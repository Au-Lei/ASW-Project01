"""Strict, field-level scoring for private booking-document evaluation sets."""

from app.state import FIELDS


def _comparable(value: str) -> str:
    return " ".join(value.strip().casefold().split())


def score_case(expected: dict[str, str], actual: dict[str, dict]) -> dict:
    if set(expected) != set(FIELDS):
        missing = set(FIELDS) - set(expected)
        extra = set(expected) - set(FIELDS)
        raise ValueError(f"标准答案必须包含全部八个字段；缺少 {sorted(missing)}，多余 {sorted(extra)}")
    fields = {}
    for key in FIELDS:
        gold = str(expected[key])
        value = str(actual.get(key, {}).get("value", ""))
        if _comparable(value) == _comparable(gold):
            status = "correct" if gold.strip() else "correct_blank"
        elif not value.strip():
            status = "missed"
        else:
            status = "wrong_value"
        fields[key] = {"status": status, "expected": gold, "actual": value}
    return {"all_correct": all(entry["status"].startswith("correct") for entry in fields.values()), "fields": fields}


def summarize_cases(cases: list[dict]) -> dict:
    statuses = ("correct", "correct_blank", "missed", "wrong_value")
    by_field = {key: {status: 0 for status in statuses} for key in FIELDS}
    for case in cases:
        for key in FIELDS:
            by_field[key][case["fields"][key]["status"]] += 1
    counts = {status: sum(field[status] for field in by_field.values()) for status in statuses}
    return {
        "cases": len(cases),
        "all_correct_cases": sum(case["all_correct"] for case in cases),
        "fields": counts,
        "by_field": by_field,
    }
