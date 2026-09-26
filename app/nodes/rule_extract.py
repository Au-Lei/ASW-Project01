"""Rule based fallback extraction for demos without an API key."""

import re

from app.state import FIELDS


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
        return f"{month}.{int(english.group(1)):02d}"
    match = re.search(r"(?:(?:20\d{2})[-/.年])?\s*(\d{1,2})\s*[-/.月]\s*(\d{1,2})", value)
    return f"{int(match.group(1))}.{int(match.group(2)):02d}" if match else value.strip()


def rule_extract(text: str) -> dict:
    """Conservative fallback for text PDFs and Office documents."""
    text = split_inline_fields(text)
    result = {key: {"value": "", "evidence": ""} for key in FIELDS}
    patterns = {
        "bl_number": [r"(?m)^\s*(?:BOOKING NUMBER(?:\([^)]*\))?|Booking No\.|订舱号码|订舱号|提\s*单\s*号|提单号)\s*[:：]\s*(?:\|\s*)?([A-Z0-9-]{7,})"],
        "sailing_date": [r"(?m)(?:^|\|)[ \t]*(?:ETD(?: DATE)?|预计开航时间|预计开航日|预计船期|预计开船日|开船时间|船期)[ \t]*[:：]?[ \t]*(?:\|[ \t]*)?((?:20\d{2}[-/.年])?\d{1,2}[-/.月]\d{1,2}|\d{1,2}[ -][A-Z]{3}[ -]20\d{2})", r"(?m)^.+\s+(?:\d+[A-Z])\s+(20\d{2}-\d{1,2}-\d{1,2})\s+20\d{2}-"],
        "containers": [r"(?m)^\s*(?:DESPATCH QUANTITY FCL QTY|箱型/箱量|箱型箱量|箱量及类型|箱量|箱型|数量)\s*[:：]?\s*(?:\|\s*)?(\d+\s*[xX*×/]?\s*40\s*'?\s*(?:HQ|HC|RH|NOR|HI-CUBE|GP)|\d+\s*[xX*×/]?\s*20\s*'?\s*(?:GP|DRY|DC)|(?:20|40)\s*'?(?:HQ|HC|RH|NOR|GP|DRY)\s*[xX*×]\s*\d+|LCL)", r"\b(\d+\s*[xX*×/]\s*(?:20|40)\s*'?(?:HQ|HC|RH|NOR|GP|DRY))\b", r"(?m)^\s*(\d+\s+20\s+DRY)\s", r"(?m)^\s*(\d+\s*/\s*40'\s*HI-CUBE)\b"],
        "station": [r"(?m)^\s*(?:入货场站|场站|提箱场地|提箱场站|提空地点)\s*[:：]\s*(?:\|\s*)?([^\r\n|]{2,60})"],
        "destination": [r"(?m)^[ \t]*(?:PORT OF DISCHARGE|POD|卸货港|目的港|目[ \t]*的[ \t]*港)(?:/卸货地|[ \t]*\([^)]*\))?[ \t]*[:：]?[ \t]*(?:\|[ \t]*)?([A-Za-z][A-Za-z ,.-]{2,60})", r"(?:目\s*的\s*港|卸\s*货\s*港|PORT OF DISCHARGE)(?:\s*\([^)]*\))?\s*[:：]\s*(?:\|\s*)?([A-Za-z][A-Za-z ,.-]{2,60})", r"交货地[ \t]*[:：][ \t]*([A-Za-z][A-Za-z ,.-]{2,60})"],
        "origin": [r"(?m)^[ \t]*(?:PORT OF LOADING|POL|装货港|装运港|起运港)(?:/起运地|[ \t]*\([^)]*\))?[ \t]*[:：]?[ \t]*(?:\|[ \t]*)?([A-Za-z][A-Za-z ,.-]{2,60})", r"收货地[ \t]*[:：][ \t]*([A-Za-z][A-Za-z ,.-]{2,60})"],
    }
    for key, pats in patterns.items():
        value, evidence = match_first(text, pats)
        if key == "sailing_date" and value:
            value = format_date(value)
        if key == "containers" and value:
            reversed_quantity = re.fullmatch(r"(20|40)\s*'?(HQ|HC|RH|NOR|GP|DRY)\s*[xX*×]\s*(\d+)", value, re.I)
            if reversed_quantity:
                value = f"{reversed_quantity.group(3)}X{reversed_quantity.group(1)}{reversed_quantity.group(2)}"
            value = re.sub(r"\s+", "", value.upper()).replace("*", "X").replace("×", "X").replace("'", "")
            value = re.sub(r"^(\d+)(?=20|40)", r"\1X", value)
            value = value.replace("20DRY", "20GP").replace("40HI-CUBE", "40HC").replace("/", "X")
        if key in {"destination", "origin"} and value:
            value = re.split(r"(?:\s+(?:ETA|ETD|SI CUT|VGM|Cut-Off)|https?)(?:\s|:|$)", value, 1, flags=re.I)[0].strip(" /,.")
            value = re.sub(r"\s+SI$", "", value, flags=re.I)
        result[key] = {"value": value, "evidence": evidence}
    vessel, voyage = match_first(text, [r"(?m)^\s*(?:INTENDED VESSEL/VOYAGE|VESSEL/VOYAGE|船名/航次|船名航次)(?:\([^)]*\))?\s*[:：]\s*(?:\|\s*)?([^\r\n|]{4,80})", r"(?m)^\s*船名\s*[:：]\s*([^\r\n|]{4,80})"])
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
    if not result["containers"]["value"] and re.search(r"\bLCL\b", text, re.I):
        result["containers"] = {"value": "LCL", "evidence": "LCL"}
    return result

