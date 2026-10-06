"""Select source candidates using conservative company priorities."""

import re
from app.business import CONTAINER_EQUIVALENTS
from app.nodes.normalize import normalize_origin
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


def merge_candidates(extracted: list[tuple[dict, dict]]) -> dict:
    extracted = sorted(extracted, key=lambda item: item[0]["role"] == "入货通知", reverse=True)
    fields = {}
    for key in FIELDS:
        candidates = [(document, values[key]) for document, values in extracted if values[key]["value"]]
        if key == "bl_number":
            candidates.sort(key=lambda item: item[1].get("identifier_kind") == "bill", reverse=True)
        if candidates:
            document, choice = candidates[0]
            conflict = len(candidates) == 2 and comparable_value(key, candidates[0][1]["value"]) != comparable_value(key, candidates[1][1]["value"])
            if key == "bl_number" and conflict:
                conflict = candidates[0][1].get("identifier_kind") == candidates[1][1].get("identifier_kind")
            alternatives = [{"value": entry["value"], "source": source["name"],
                             "evidence": entry.get("evidence", ""), "role": source["role"]}
                            for source, entry in candidates]
            fields[key] = {**choice, "source": document["name"], "conflict": bool(conflict),
                           "candidates": alternatives}
        else:
            fields[key] = {"value": "", "evidence": "", "source": "", "conflict": False}
    return fields
