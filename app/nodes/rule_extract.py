"""Rule based fallback extraction for demos without an API key."""

import re

from app.state import FIELDS


def normalize_source_text(text: str) -> str:
    """Old Word files use bare CRs and table control characters as separators."""
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\xa0", " ")
    return re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "\n", text)


def split_inline_fields(text: str) -> str:
    """PDF tables often place two labeled cells on the same extracted line."""
    labels = r"(?:提\s*单\s*号|订舱号|船名/航次|船名航次|船期|箱量及类型|箱型/箱量|箱型箱量|箱量|场站|目的港|装货港|起运港|PORT OF DISCHARGE|PORT OF LOADING)"
    return re.sub(rf"[ \t]+(?={labels}[ \t]*[:：])", "\n", text, flags=re.I)


def match_first(text: str, patterns: list[str]) -> tuple[str, str]:
    for pattern in patterns:
        for match in re.finditer(pattern, text, re.I | re.M):
            value = re.sub(r"\s+", " ", match.group(1)).strip(" :：/|,，")
            if value and not value.upper().startswith(("PORT OF ", "POD", "POL")):
                return value, match.group(0).strip()[:180]
    return "", ""


def format_date(value: str) -> str:
    english = re.search(r"(\d{1,2})[ -](JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)[ -]20\d{2}", value, re.I)
    if english:
        month = ("JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC").index(english.group(2).upper()) + 1
        return f"{month}.{int(english.group(1))}"
    match = re.search(r"(?:(?:20\d{2})[-/.年])?\s*(\d{1,2})\s*[-/.月]\s*(\d{1,2})", value)
    return f"{int(match.group(1))}.{int(match.group(2))}" if match else value.strip()


def match_route(text: str) -> tuple[str, str, str]:
    """Read a port-to-port route only when both sides are explicitly present."""
    pattern = r"(?m)^([^\r\n:：|]{2,60}?)[ \t]*(?:--|—|–|→|\bTO\b)[ \t]*([^\r\n|]{2,60})[ \t]*$"
    for match in re.finditer(pattern, text):
        origin = match.group(1).strip()
        destination = match.group(2).strip()
        origin = re.sub(r"^.*?(?:出口|航线|路线|订舱的)\s*", "", origin).strip()
        if re.search(r"\b(?:QINGDAO|TIANJIN|SHANGHAI|NINGBO|DALIAN|SHENZHEN|XIAMEN)\b", origin, re.I) and re.match(r"[A-Za-z]", destination):
            return origin, destination, match.group(0).strip()[:180]
    return "", "", ""


def normalize_station(value: str) -> str:
    """Drop a legal-company suffix, not the identifying yard name."""
    value = re.split(r"(?:码头/堆场热线|联系电话|电话)[：:]?", value, 1)[0].strip()
    value = re.sub(r"[（(](?:暂定|待定|以实际为准)[^）)]*[）)]", "", value).strip()
    if value in {"青岛港联荣場站", "青岛港联荣场站"}:
        return "青岛港"
    return re.sub(r"(?:物流)?有限公司$", "", value)


def rule_extract(text: str) -> dict:
    """Conservative fallback for text PDFs and Office documents."""
    text = split_inline_fields(normalize_source_text(text))
    result = {key: {"value": "", "evidence": ""} for key in FIELDS}
    bill, bill_evidence = match_first(text, [r"(?m)^[ \t]*(?:提\s*单\s*号|B/L[ \t]*(?:NO\.?|NUMBER)|BILL OF LADING[ \t]*(?:NO\.?|NUMBER)|D/R[ \t]*NO\.?)\s*[:：.]?\s*(?:\|\s*)?([A-Z0-9-]{7,})"])
    booking, booking_evidence = match_first(text, [r"(?m)^[ \t]*(?:BOOKING NUMBER(?:\([^)]*\))?|Booking No\.?|订舱号码|订舱号|SO/NO)\s*[:：.]?\s*(?:\|\s*)?([A-Z0-9-]{7,})", r"\bElectronic Ref\.[ \t]*:[ \t]*([A-Z0-9-]{7,})"])
    result["bl_number"] = {"value": bill or booking, "evidence": bill_evidence or booking_evidence, "identifier_kind": "bill" if bill else "booking" if booking else ""}
    patterns = {
        "sailing_date": [r"\bPROFORMA[ \t]+ETD[ \t]*:[ \t]*(\d{1,2}[ -][A-Z]{3}[ -]20\d{2})", r"(?m)^[ \t]*(?:VSL/VOY|VESSEL/VOYAGE):[^\n]{1,100}?\bETD:[ \t]*((?:20\d{2}[-/.])\d{1,2}[-/.]\d{1,2})", r"(?m)^[ \t]*Port of Loading:[^\n]{1,100}?\bETD:[ \t]*(\d{1,2}[ -][A-Z]{3}[ -]20\d{2})", r"预计开航[ \t]*[:：][ \t]*((?:20\d{2}[-/.年])?\d{1,2}[-/.月]\d{1,2})", r"(?m)(?:^|\|)[ \t]*(?:ETD(?: DATE)?|预计开航时间|预计开航日|预计开航|预计船期|预计开船期|预计开船日|开船时间|船期)[ \t]*[:：]?[ \t]*(?:\|[ \t]*)?((?:20\d{2}[-/.年])?\d{1,2}[-/.月]\d{1,2}|\d{1,2}[ -][A-Z]{3}[ -]20\d{2})", r"(?m)^.+\s+(?:\d+[A-Z])\s+(20\d{2}-\d{1,2}-\d{1,2})\s+20\d{2}-"],
        "containers": [r"(?m)^\s*(?:DESPATCH QUANTITY FCL QTY|箱型/箱量|箱型箱量|箱量及类型|箱量|箱型|数量)\s*[:：]?\s*(?:\|\s*)?(\d+\s*[xX*×/]?\s*40\s*'?\s*(?:HQ|HC|RH|NOR|REEF|HI-CUBE|GP)|\d+\s*[xX*×/]?\s*20\s*'?\s*(?:GP|DV|DRY|DC)|(?:20|40)\s*'?(?:HQ|HC|RH|NOR|REEF|GP|DV|DRY)\s*[xX*×]\s*\d+|LCL)", r"\b(\d+\s*[xX*×/]\s*(?:20|40)\s*'?(?:HQ|HC|RH|NOR|REEF|GP|DV|DRY))\b", r"(?m)^\s*(\d+\s+20\s+DRY)\s", r"(?m)^\s*(\d+\s*/\s*40'\s*HI-CUBE)\b"],
        "station": [r"(?m)^\s*(?:入货场站|场站|提箱场地|提箱场站|提箱堆场|提空地点|提柜地点|DEPOT)\s*[:：]\s*(?:\|\s*)?([^\r\n|]{2,60})"],
        "destination": [r"(?m)^[ \t]*(?:PORT OF DISCHARGE|DISCHARGING PORT|POD|卸货港|目的港|目[ \t]*的[ \t]*港)(?:/卸货地|[ \t]*\([^)]*\))?[ \t]*[:：]?[ \t]*(?:\|[ \t]*)?([A-Za-z][A-Za-z ,.-]{2,60})", r"(?:目\s*的\s*港|卸\s*货\s*港|PORT OF DISCHARGE)(?:\s*\([^)]*\))?\s*[:：]\s*(?:\|\s*)?([A-Za-z][A-Za-z ,.-]{2,60})", r"交货地[ \t]*[:：][ \t]*([A-Za-z][A-Za-z ,.-]{2,60})"],
        "origin": [r"(?m)^[ \t]*(?:PORT OF LOADING|LOADING PORT|POL|装货港|装运港|起运港)(?:/起运地|[ \t]*\([^)]*\))?[ \t]*[:：]?[ \t]*(?:\|[ \t]*)?([A-Za-z][A-Za-z ,.-]{2,60})", r"收货地[ \t]*[:：][ \t]*([A-Za-z][A-Za-z ,.-]{2,60})"],
    }
    for key, pats in patterns.items():
        value, evidence = match_first(text, pats)
        if key == "sailing_date" and value:
            value = format_date(value)
        if key == "containers" and value:
            reversed_quantity = re.fullmatch(r"(20|40)\s*'?(HQ|HC|RH|NOR|REEF|GP|DV|DRY)\s*[xX*×]\s*(\d+)", value, re.I)
            if reversed_quantity:
                value = f"{reversed_quantity.group(3)}X{reversed_quantity.group(1)}{reversed_quantity.group(2)}"
            value = re.sub(r"\s+", "", value.upper()).replace("*", "X").replace("×", "X").replace("'", "")
            value = re.sub(r"^(\d+)(?=20|40)", r"\1X", value)
            value = value.replace("20DRY", "20GP").replace("40HI-CUBE", "40HC").replace("/", "X")
            if "40REEF" in value and re.search(r"(?:40\s*REEF.{0,30}(?:冻代干|冷代干)|(?:冻代干|冷代干).{0,30}40\s*REEF)", text, re.I):
                value = value.replace("40REEF", "40NOR")
        if key in {"destination", "origin"} and value:
            value = re.split(r"(?:\s+(?:ETA|ETD|SI CUT|VGM|Cut-Off)|https?)(?:\s|:|$)", value, 1, flags=re.I)[0].strip(" /,.")
            value = re.sub(r"\s+SI$", "", value, flags=re.I)
            if key == "destination":
                value = re.sub(r",\s*(?:(?:SOUTH\s+)?KOREA|INDIA|QC)$", "", value, flags=re.I)
        if key == "station" and value:
            value = normalize_station(value)
        result[key] = {"value": value, "evidence": evidence}
    route_origin, route_destination, route_evidence = match_route(text)
    if route_origin and not result["origin"]["value"]:
        result["origin"] = {"value": route_origin, "evidence": route_evidence}
    if route_destination and not result["destination"]["value"]:
        result["destination"] = {"value": re.sub(r",?\s+(?:SOUTH\s+)?KOREA$", "", route_destination, flags=re.I), "evidence": route_evidence}
    if not result["origin"]["value"] and result["station"]["value"] == "青岛港" and "青岛港联荣" in result["station"]["evidence"]:
        result["origin"] = {"value": "QD", "evidence": result["station"]["evidence"] + "（由场站推断，需核对）"}
    if not result["containers"]["value"]:
        pickup_quantity = re.search(r"(?mi)^相关提柜地点[ \t]*\n[ \t]*(20|40)[ \t]*'[ \t]*(DRY VAN|DRY|GP|DV)[ \t]*\n[ \t]*(\d+)[ \t]*\n[ \t]*Total[ \t]+\3\b", text)
        if pickup_quantity:
            result["containers"] = {"value": f"{pickup_quantity.group(3)}X{pickup_quantity.group(1)}GP", "evidence": pickup_quantity.group(0)[:180]}
    if not result["containers"]["value"]:
        table_quantity = re.search(r"(?mi)^Container Type / Size[^\n]*\n[ \t]*(20|40)[ \t]*(GP|HC|HQ|NOR|RH)\b([^\n]{0,100}?)\bX[ \t]*(\d+)\b", text)
        if table_quantity:
            result["containers"] = {"value": f"{table_quantity.group(4)}X{table_quantity.group(1)}{table_quantity.group(2).upper()}", "evidence": table_quantity.group(0)[:180]}
    if not result["containers"]["value"] and text.count("电子箱单凭证(按箱)") == 1 and "箱唯一标识" in text:
        single_box = re.search(r"(?m)^[ \t]*箱型/箱量[ \t]*[:：][ \t]*(20|40)[ \t]*(GP|HC|HQ|NOR|RH)\b", text, re.I)
        if single_box:
            result["containers"] = {"value": f"1X{single_box.group(1)}{single_box.group(2).upper()}", "evidence": "电子箱单凭证(按箱)；" + single_box.group(0).strip()}
    vessel, voyage = match_first(text, [r"(?m)^\s*(?:INTENDED VESSEL/VOYAGE|VESSEL/VOYAGE|VSL/VOY|船名/航次|船名航次)(?:\([^)]*\))?\s*[:：]\s*(?:\|\s*)?([^\r\n|]{4,80})", r"(?m)^\s*船名\s*[:：]\s*([^\r\n|]{4,80})"])
    if vessel:
        vessel = re.split(r"\s+(?:ETD|ETA|CARRIER|预计)", vessel, 1, flags=re.I)[0]
        vessel = re.sub(r"\(\)\s*/", " / ", vessel)
        vessel = re.sub(r"\s+航次\s*[:：]\s*", " / ", vessel)
        special = re.match(r"(.+?)\s+(\d+\s+[A-Z]\d+)\s*$", vessel, re.I)
        if special:
            result["vessel"] = {"value": special.group(1), "evidence": voyage}
            result["voyage"] = {"value": special.group(2), "evidence": voyage}
            return result
        split = re.match(r"(.+?)\s+(?:V\.)?(\d[A-Z0-9/-]{2,})\s*$", vessel, re.I)
        if split:
            result["vessel"] = {"value": split.group(1).strip(" /"), "evidence": voyage}
            result["voyage"] = {"value": split.group(2), "evidence": voyage}
        else:
            split = re.match(r"(.+?)\s*/\s*([A-Z0-9/-]{3,})\s*$", vessel, re.I)
            if split:
                result["vessel"] = {"value": split.group(1), "evidence": voyage}
                result["voyage"] = {"value": split.group(2), "evidence": voyage}
            else:
                result["vessel"] = {"value": vessel.strip(), "evidence": voyage}
    if not result["voyage"]["value"]:
        v, e = match_first(text, [r"(?m)^\s*航次\s*[:：]\s*([A-Z0-9/-]{3,})"])
        result["voyage"] = {"value": v, "evidence": e}
    return result
