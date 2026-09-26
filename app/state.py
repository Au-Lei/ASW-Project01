"""Shared field definitions and paths for the extraction workflow."""

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = PROJECT_ROOT / "assets" / "业务联系单模板.xlsx"
MAX_DOCUMENT_BYTES = 12 * 1024 * 1024
FIELDS = ("bl_number", "vessel", "voyage", "sailing_date", "containers", "station", "destination", "origin")
CELLS = {"bl_number": "B8", "vessel": "B9", "voyage": "E9", "sailing_date": "B10", "containers": "B11", "station": "B12", "destination": "B13", "origin": "E13"}
LABELS = {"bl_number": "提单号/订舱号", "vessel": "船名", "voyage": "航次", "sailing_date": "船期", "containers": "箱量及类型", "station": "场站", "destination": "目的港", "origin": "起运港"}
