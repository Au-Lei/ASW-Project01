"""Export reviewed values and persist only explicitly confirmed aliases."""

from app.tools.alias_memory import remember_aliases
from app.tools.excel_export import make_workbook


def export_review(payload: dict) -> tuple[bytes, bool]:
    values = payload.get("values", {})
    aliases = payload.get("confirmed_aliases", [])
    if not isinstance(values, dict) or any(not isinstance(value, str) for value in values.values()):
        raise ValueError("审核字段格式无效")
    if not isinstance(aliases, list):
        raise ValueError("字段别名格式无效")
    data = make_workbook(values)
    candidates = [item for item in aliases if isinstance(item, dict)
                  and item.get("confirmed") is True
                  and isinstance(item.get("field"), str) and values.get(item["field"], "").strip()
                  and not any(value.strip() and len(value.strip()) >= 3
                              and value.strip().casefold() in str(item.get("source_label", "")).casefold()
                              for value in values.values())]
    try:
        remember_aliases(candidates)
    except OSError:
        return data, True
    return data, False
