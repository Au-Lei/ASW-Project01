"""Write confirmed values into the supplied Excel template."""

import io

import openpyxl

from app.state import CELLS, MANUAL_CELLS, TEMPLATE


def make_workbook(values: dict[str, str]) -> bytes:
    if not TEMPLATE.exists():
        raise ValueError("业务联系单模板文件不存在")
    wb = openpyxl.load_workbook(TEMPLATE)
    sheet = wb["业务联系单"]
    for key, address in {**CELLS, **MANUAL_CELLS}.items():
        value = str(values.get(key, "")).strip()[:160]
        if value.startswith(("=", "+", "-", "@")):
            value = "'" + value
        sheet[address] = value
    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()
