"""Rule based fallback extraction for demos without an API key."""

import re

from app.state import FIELDS
from app.rules.patterns import FIELD_PATTERNS


def normalize_source_text(text: str) -> str:
    """Old Word files use bare CRs and table control characters as separators."""
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\xa0", " ")
    return re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "\n", text)


def split_inline_fields(text: str) -> str:
    """PDF tables often place two labeled cells on the same extracted line."""
    labels = r"(?:提\s*单\s*号|订舱号|船名/航次|船名航次|船期|箱量及类型|箱型/箱量|箱型箱量|箱型箱数|箱量|提箱地点|提箱地|提柜地点|场站|目的港|装货港|起运港|ETD|PORT OF DISCHARGE|PORT OF LOADING)"
    return re.sub(rf"[ \t]+(?={labels}[ \t]*[:：])", "\n", text, flags=re.I)


def match_first(text: str, patterns: list[str]) -> tuple[str, str]:
    for pattern in patterns:
        for match in re.finditer(pattern, text, re.I | re.M):
            value = re.sub(r"\s+", " ", match.group(1)).strip(" :：/|,，")
            if value and not value.upper().startswith(("PORT OF ", "POD", "POL")):
                return value, match.group(0).strip()[:180]
    return "", ""


def collect_matches(text: str, patterns: list[str]) -> list[dict]:
    """Keep every explicit match for later comparison, not just the first one."""
    found = []
    for priority, pattern in enumerate(patterns):
        for match in re.finditer(pattern, text, re.I | re.M):
            value = re.sub(r"\s+", " ", match.group(1)).strip(" :：/|,，")
            if value and not value.upper().startswith(("PORT OF ", "POD", "POL")):
                found.append({"value": value, "evidence": match.group(0).strip()[:180], "pattern_priority": priority})
    return found


def format_date(value: str) -> str:
    month_first = re.search(r"\b(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)[ -](\d{1,2})[ -]20\d{2}\b", value, re.I)
    if month_first:
        month = ("JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC").index(month_first.group(1).upper()) + 1
        return f"{month}.{int(month_first.group(2))}"
    compact_english = re.search(r"\b(\d{1,2})(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)\d{2}\b", value, re.I)
    if compact_english:
        month = ("JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC").index(compact_english.group(2).upper()) + 1
        return f"{month}.{int(compact_english.group(1))}"
    english = re.search(r"(\d{1,2})[ -](JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)[ -]20\d{2}", value, re.I)
    if english:
        month = ("JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC").index(english.group(2).upper()) + 1
        return f"{month}.{int(english.group(1))}"
    day_first = re.search(r"\b(\d{1,2})\.(\d{1,2})\.20\d{2}\b", value)
    if day_first:
        return f"{int(day_first.group(2))}.{int(day_first.group(1))}"
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
    if value.startswith("山港陆海联地"):
        return "山港陆海联地"
    if value.startswith("山東港口陸海國際物流日照"):
        return value
    return re.sub(r"(?:物流)?有限公司$", "", value)


def _labeled_value(text: str, label: str, value: str) -> tuple[str, str]:
    """Read a label and value even when an Office table puts them on separate lines."""
    match = re.search(rf"(?mi)^[ \t]*(?:{label})[ \t]*[:：]?[ \t]*(?:\|[ \t]*)?(?:\n[ \t]*){{0,3}}({value})", text)
    return (match.group(1).strip(), match.group(0).strip()[:180]) if match else ("", "")


def _complete_sparse_fields(text: str, result: dict) -> None:
    """Handle common carrier layouts left intact by text extraction."""
    def put(key: str, value: str, evidence: str, **extra: str) -> None:
        if value and not result[key]["value"]:
            result[key] = {"value": value, "evidence": evidence, **extra}

    bill, evidence = _labeled_value(text, r"Bill of Lading\s*#|D/R\s*No\.?(?:\s*\([^)]*\))?", r"[A-Z0-9-]{7,}")
    if bill and not re.search(r"\d", bill):
        bill, evidence = "", ""
    inline_bill = re.search(r"(?i)Bill of Lading\s*#\s*:\s*([A-Z0-9-]{7,})", text)
    if inline_bill:
        bill, evidence = inline_bill.group(1), inline_bill.group(0)[:180]
    if not bill:
        match = re.search(r"(?mi)^D/R No\.[^\n]*\n(?:[^\n]*\n){0,5}?((?=[A-Z0-9]*\d)[A-Z0-9]{12,})[ \t]*$", text)
        if match:
            bill, evidence = match.group(1), match.group(0)[:180]
    if bill and result["bl_number"].get("identifier_kind") != "bill":
        result["bl_number"] = {"value": bill, "evidence": evidence, "identifier_kind": "bill"}
    if re.fullmatch(r"\d{10}", result["bl_number"]["value"]) and "OOCL" in text.upper():
        result["bl_number"]["value"] = "OOLU" + result["bl_number"]["value"]
        result["bl_number"]["evidence"] += "（OOCL 提单前缀）"

    if not result["sailing_date"]["value"]:
        date, evidence = _labeled_value(text, r"(?:预计开航时间|预计开船日|预计开船期|预计船期|ETD(?: DATE)?)", r"(?:20\d{2}[-/.]\d{1,2}[-/.]\d{1,2}|\d{1,2}[-/.]\d{1,2}[-/.]20\d{2}|\d{1,2}[-/.]\d{1,2}|\d{1,2}[- ](?:JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)[- ]20\d{2})")
        if not date:
            inline_date = re.search(r"(?i)\bETD\s*:\s*(20\d{2}[-/.]\d{1,2}[-/.]\d{1,2})", text)
            if inline_date:
                date, evidence = inline_date.group(1), inline_date.group(0)[:180]
        if not date:
            inline_date = re.search(r"预计开航时间\s*[:：]\s*(\d{1,2}[- ](?:JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)[- ]20\d{2})", text, re.I)
            if inline_date:
                date, evidence = inline_date.group(1), inline_date.group(0)[:180]
        put("sailing_date", format_date(date), evidence)
    # A first-leg ETA is not a sailing date: only an explicit ETD may fill it.
    if not result["sailing_date"]["value"] and re.search(r"(?mi)^Pre Carrier\s*:", text):
        result["sailing_date"]["review_reason"] = "仅见首程船 ETA，未找到明确的起运港 ETD，请人工核对"

    if not result["containers"]["value"]:
        box_patterns = (
            r"(?mi)(?:总箱型/尺寸|BOOKING QTY SIZE/TYPE)\s*:\s*(\d+)\s*[X*×]\s*(20|40)'?\s*(Hi-Cube|HC|HQ|GP|REEF|NOR)",
            r"(?mi)^\s*(\d+)\s+(20|40)\s+(REEF|NOR|HC|HQ|GP)\b",
        )
        for pattern in box_patterns:
            match = re.search(pattern, text)
            if match:
                qty, size, kind = match.groups()
                kind = {"HI-CUBE": "HC", "REEF": "NOR" if re.search(r"(?m)^NOR\s*$|冻代干|冷代干", text, re.I) else "REEF"}.get(kind.upper(), kind.upper())
                put("containers", f"{qty}X{size}{kind}", match.group(0)[:180])
                break
    if not result["containers"]["value"]:
        match = re.search(r"(?mi)^箱型箱数\s*[:：]\s*(20|40)(GP|DV|HC|HQ|NOR|REEF)\s*[xX*×]\s*(\d+)", text)
        if match:
            kind = "GP" if match.group(2).upper() == "DV" else match.group(2).upper()
            put("containers", f"{match.group(3)}X{match.group(1)}{kind}", match.group(0)[:180])
    if not result["containers"]["value"]:
        match = re.search(r"(?mi)^EQ Type/Q'ty\s*:\s*(20|40)'?\s*DRY\s*(HC|HQ|GP)?\.?\s*-\s*(\d+)", text)
        if match:
            put("containers", f"{match.group(3)}X{match.group(1)}{match.group(2) or 'GP'}", match.group(0)[:180])
    if not result["containers"]["value"]:
        match = re.search(r"(?mi)^\s*(20|40)(HC|HQ|GP|NOR)\s*[xX*×]\s*\n?\s*(\d+)\s*$", text)
        if match:
            put("containers", f"{match.group(3)}X{match.group(1)}{match.group(2)}", match.group(0)[:180])
    if not result["containers"]["value"] and "拼箱货物" in text:
        put("containers", "LCL", "拼箱货物（按拼箱业务类型；请核对）")

    if not result["station"]["value"]:
        station, evidence = _labeled_value(text, r"(?:提箱地点|提箱地|提柜地点|入货地址|退箱/提箱处|空箱提取处|空箱提领处|空箱提領處)", r"[^\n|]{2,100}")
        put("station", normalize_station(station.split(" 天津港")[0].split("(黄岛")[0]), evidence)

    if not result["vessel"]["value"]:
        vessel, evidence = _labeled_value(text, r"(?:Pre Carrier|Ocean Vessel\([^)]*\)\s*Voy\. No\. \([^)]*\)|船名/航次|船名航次)", r"[A-Z][A-Z0-9 .-]+(?:/|-V\.|[ \t])[ \t]*[A-Z0-9/-]{3,}")
        if not vessel:
            match = re.search(r"(?mi)^Ocean Vessel[^\n]*\n\s*([A-Z][A-Z ]+\s+-V\.\d+[A-Z])", text)
            if match:
                vessel, evidence = match.group(1), match.group(0)[:180]
        vessel = re.split(r"\s+Latest\s+ETA|\s+ETD\s*:", vessel, 1, flags=re.I)[0]
        match = re.match(r"(.+?)[ \t]*(?:/|[ \t]+-V\.|[ \t]+)(\d[A-Z0-9/-]{2,})[ \t]*$", vessel)
        if match:
            put("vessel", match.group(1).strip(), evidence)
            put("voyage", match.group(2).strip(), evidence)
    if result["vessel"]["value"] and not result["voyage"]["value"]:
        match = re.search(r"(?mi)^船名/航次:[^\n]*\n(?:[^\n]*\n){0,2}[ \t]*(\d{2,5}[A-Z])[ \t]*$", text)
        if match:
            put("voyage", match.group(1), match.group(0)[:180])
    if result["station"]["value"].startswith("点:") or result["station"]["value"].startswith("点："):
        result["station"]["value"] = normalize_station(result["station"]["value"][2:].split(" 天津港")[0].strip())

    if not result["origin"]["value"]:
        origin, evidence = _labeled_value(text, r"(?:FROM|Place of Receipt|接货地|收货地|Port of Loading|装港)", r"[A-Z][A-Z ,.'-]{2,70}")
        put("origin", origin, evidence)
    if not result["destination"]["value"]:
        destination, evidence = _labeled_value(text, r"(?:目的港|Port of Discharge(?:\s*\([^)]*\))?|卸港)", r"[A-Z][A-Z ,.'-]{2,70}")
        if not re.match(r"(?:Place of |Port of |Final Destination|Ocean Vessel)", destination, re.I):
            put("destination", destination, evidence)
    if re.search(r"(?mi)^PLACE OF RECEIPT\s*:\s*Zhengzhou", text) and re.search(r"(?mi)^PORT OF LOADING\s*:\s*Qingdao", text):
        result["origin"] = {"value": "ZZ-QD", "evidence": "PLACE OF RECEIPT: Zhengzhou；PORT OF LOADING: Qingdao"}
    if re.search(r"(?mi)^Pre Carrier\s*:", text) and re.search(r"(?mi)^Place of Receipt\s*:\s*NANSHA", text):
        result["origin"] = {"value": "NS", "evidence": "Place of Receipt: NANSHA（首程收货地；请核对）"}


def rule_extract(text: str) -> dict:
    """Conservative fallback for text PDFs and Office documents."""
    text = split_inline_fields(normalize_source_text(text))
    result = {key: {"value": "", "evidence": ""} for key in FIELDS}
    bill, bill_evidence = match_first(text, [r"(?m)^[ \t]*(?:提\s*单\s*号|B/L[ \t]*(?:NO\.?|NUMBER)|BILL OF LADING[ \t]*(?:NO\.?|NUMBER)|D/R[ \t]*NO\.?)\s*[:：.]?\s*(?:\|\s*)?([A-Z0-9-]{7,})"])
    booking, booking_evidence = match_first(text, [r"(?m)^[ \t]*(?:BOOKING NUMBER(?:\([^)]*\))?|Booking No\.?|订舱号码|订舱号|SO/NO)\s*[:：.]?\s*(?:\|\s*)?([A-Z0-9-]{7,})", r"\bElectronic Ref\.[ \t]*:[ \t]*([A-Z0-9-]{7,})"])
    result["bl_number"] = {"value": bill or booking, "evidence": bill_evidence or booking_evidence, "identifier_kind": "bill" if bill else "booking" if booking else ""}
    for key, pats in FIELD_PATTERNS.items():
        value, evidence = ("", "")
        if key == "sailing_date":
            value, evidence = match_first(text, [
                r"(?mi)^Port of Loading[^\n]{0,140}?\bETD\s*:\s*(\d{1,2}[ -][A-Z]{3}[ -]20\d{2}|20\d{2}[-/.]\d{1,2}[-/.]\d{1,2}|\d{1,2}[A-Z]{3}\d{2})",
                r"(?i)Proforma\s+1st\s+vessel\s+ETD\s*:\s*(\d{1,2}[A-Z]{3}\d{2}|\d{1,2}[ -][A-Z]{3}[ -]20\d{2})",
            ])
        if not value:
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
            _complete_sparse_fields(text, result)
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
    _complete_sparse_fields(text, result)
    return result


def rule_candidates(text: str, result: dict) -> dict[str, list[dict]]:
    """Collect competing labeled values while retaining legacy fallbacks as candidates."""
    text = split_inline_fields(normalize_source_text(text))
    candidates = {key: [] for key in FIELDS}
    bill_patterns = [
        r"(?mi)^[ \t]*(?:主提单号|提\s*单\s*号|B/L[ \t]*(?:NO\.?|NUMBER)|BILL OF LADING[ \t]*(?:NO\.?|NUMBER)|D/R[ \t]*NO\.?)\s*[:：.]?\s*(?:\|\s*)?([A-Z0-9-]{7,})",
        r"(?mi)^\s*(?:BOOKING NUMBER(?:\([^)]*\))?|Booking No\.?|订舱号码|订舱号|SO/NO)\s*[:：.]?\s*(?:\|\s*)?([A-Z0-9-]{7,})",
    ]
    for index, item in enumerate(collect_matches(text, bill_patterns)):
        item["identifier_kind"] = "bill" if item["pattern_priority"] == 0 else "booking"
        candidates["bl_number"].append(item)
    for key in ("sailing_date", "containers", "destination", "origin"):
        candidates[key].extend(collect_matches(text, FIELD_PATTERNS[key]))
    candidates["sailing_date"].extend(collect_matches(text, [
        r"(?mi)(?:预计离港日|预计离港时间|开船日期|开航日期|ETD)\s*[:：]?\s*(20\d{2}[-/.]\d{1,2}[-/.]\d{1,2}|\d{1,2}[-/.]\d{1,2}[-/.]20\d{2}|\d{1,2}[-/.]\d{1,2}(?!\s*[-~至到]\s*\d)|[A-Z]{3}[- ]\d{1,2}[- ]20\d{2})",
    ]))
    candidates["containers"].extend(collect_matches(text, [
        r"(?mi)(?:箱量及类型|箱型/箱量|箱型箱量|箱量|箱型|柜型/数量)\s*[:：]?\s*(\d+\s*[X*×]\s*(?:20|40)\s*(?:GP|DV|HC|HQ|NOR|REEF)(?:\s*\+\s*\d+\s*[X*×]\s*(?:20|40)\s*(?:GP|DV|HC|HQ|NOR|REEF))+)",
    ]))
    for key in FIELDS:
        legacy = result.get(key, {})
        if legacy.get("value"):
            candidates[key].append({**legacy, "legacy": True})
    return candidates
