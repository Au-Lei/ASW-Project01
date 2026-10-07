"""Select source candidates using conservative company priorities."""

import re
from app.business import CONTAINER_EQUIVALENTS
from app.nodes.normalize import normalize_destination, normalize_origin, normalize_sailing_date
from app.state import FIELDS


def comparable_value(key: str, value: str) -> str:
    """Ignore harmless port spelling differences when reporting conflicts."""
    if key == "origin":
        value = normalize_origin(value)
    elif key == "destination":
        value = re.sub(r",\s*(?:SOUTH\s+)?(?:KOREA|CHINA|TURKEY)\s*$", "", value, flags=re.I)
    elif key == "containers":
        compact = re.sub(r"\s+", "", value.upper()).replace("*", "X").replace("×", "X")
        container = re.fullmatch(r"(\d+)X(20|40)(GP|DV|HQ|HC|NOR|REEF|RH)", compact)
        if container:
            box_type = CONTAINER_EQUIVALENTS.get(container.group(3), container.group(3))
            return f"{int(container.group(1))}X{container.group(2)}{box_type}"
    return re.sub(r"\s+", " ", value).strip().casefold()


def _prepare(key: str, entry: dict) -> dict:
    entry = dict(entry)
    value = str(entry.get("value", "")).strip()
    if key == "sailing_date":
        from app.nodes.rule_extract import format_date
        value = normalize_sailing_date(format_date(value))
    elif key == "destination":
        value = normalize_destination(value)
    elif key == "origin":
        value = normalize_origin(value)
    elif key == "containers":
        reversed_box = re.fullmatch(r"(20|40)'?(HQ|HC|GP|DV|NOR|REEF)\s*[xX*×]\s*(\d+)", value, re.I)
        if reversed_box:
            value = f"{reversed_box.group(3)}X{reversed_box.group(1)}{reversed_box.group(2)}"
        value = re.sub(r"\s+", "", value.upper()).replace("*", "X").replace("×", "X").replace("'", "")
        value = value.replace("HI-CUBE", "HC").replace("DRY", "GP").replace("DV", "GP")
    entry["value"] = value
    return entry


def _score(key: str, entry: dict, role: str) -> int:
    value = entry["value"]
    evidence = str(entry.get("evidence", ""))
    upper = evidence.upper()
    score = 30 + (7 if role == "入货通知" else 0)
    if entry.get("legacy"):
        score += 12 if key in {"vessel", "voyage", "station"} else 5
    if key == "bl_number":
        if not re.fullmatch(r"[A-Z0-9-]{7,24}", value.upper()) or not re.search(r"\d", value):
            return -100
        score += 30 if entry.get("identifier_kind") == "bill" else 4
        if re.search(r"\b(?:B/L|BILL OF LADING|提单号|D/R)\b", upper):
            score += 8
    elif key == "sailing_date":
        if not re.fullmatch(r"\d{1,2}\.\d{1,2}", value):
            return -100
        score += 22 if "ETD" in upper or "开航" in evidence or "开船" in evidence else 10
        if "PORT OF LOADING" in upper or "起运港" in evidence:
            score += 12
        if "PROFORMA 1ST" in upper:
            score -= 5
        if "ETA" in upper and "ETD" not in upper:
            return -100
    elif key == "containers":
        if value != "LCL" and not re.fullmatch(r"(?:[1-9]\d?X(?:20|40)(?:GP|HC|HQ|NOR|REEF|RH))(?:\+[1-9]\d?X(?:20|40)(?:GP|HC|HQ|NOR|REEF|RH))*", value):
            return -100
        score += 14 if re.search(r"箱|QTY|QUANTITY|CONTAINER", upper) else 4
        score += 10 if "+" in value else 0
        if re.search(r"\b(?:TOTAL|总计)\b", upper):
            score += 5
    elif key == "destination":
        if len(value) > 48 or re.search(r"\b(?:PORT OF|PLACE OF|VESSEL|ETD|ETA|CUT OFF)\b", value, re.I):
            return -100
        score += 15 if re.search(r"POD|DISCHARGE|目的港|卸货港", upper) else 0
    elif key == "origin":
        if len(value) > 24 or re.search(r"\b(?:PORT OF|PLACE OF|VESSEL|ETD|ETA|TEL)\b", value, re.I):
            return -100
        score += 15 if re.search(r"POL|LOADING|装货港|起运港", upper) else 0
    return score


def merge_candidates(extracted: list[tuple[dict, dict]]) -> dict:
    extracted = sorted(extracted, key=lambda item: item[0]["role"] == "入货通知", reverse=True)
    fields = {}
    for key in FIELDS:
        candidates = []
        for document, values in extracted:
            entries = document.get("rule_candidates", {}).get(key) or [values[key]]
            for entry in entries:
                if entry.get("value"):
                    prepared = _prepare(key, entry)
                    score = _score(key, prepared, document["role"])
                    if score >= 0:
                        candidates.append((document, prepared, score))
        candidates.sort(key=lambda item: item[2], reverse=True)
        distinct = []
        seen = set()
        for document, entry, score in candidates:
            marker = (document["name"], comparable_value(key, entry["value"]))
            if marker not in seen:
                distinct.append((document, entry, score))
                seen.add(marker)
        candidates = distinct
        if candidates:
            document, choice, top_score = candidates[0]
            conflict = any(comparable_value(key, choice["value"]) != comparable_value(key, entry["value"])
                           for _, entry, _ in candidates[1:])
            if key == "bl_number" and conflict:
                conflict = any(choice.get("identifier_kind") == entry.get("identifier_kind") and
                               comparable_value(key, choice["value"]) != comparable_value(key, entry["value"])
                               for _, entry, _ in candidates[1:])
            alternatives = [{"value": entry["value"], "source": source["name"],
                             "evidence": entry.get("evidence", ""), "role": source["role"], "score": score}
                            for source, entry, score in candidates]
            uncertain = (key in {"bl_number", "sailing_date", "containers", "destination", "origin"}
                         and top_score < 35)
            fields[key] = {**choice, "value": "" if uncertain else choice["value"],
                           "review_reason": "候选证据不足，请人工核对" if uncertain else choice.get("review_reason", ""),
                           "source": document["name"], "conflict": bool(conflict),
                           "candidates": alternatives}
        else:
            fields[key] = {"value": "", "evidence": "", "source": "", "conflict": False}
    return fields
