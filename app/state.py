"""Shared field definitions and paths for the extraction workflow."""

from pathlib import Path

from app.business import FIELD_DEFINITIONS


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = PROJECT_ROOT / "assets" / "业务联系单模板.xlsx"
MAX_DOCUMENT_BYTES = 12 * 1024 * 1024
FIELDS = tuple(f.key for f in FIELD_DEFINITIONS if f.automatic)
CELLS = {f.key: f.cell for f in FIELD_DEFINITIONS if f.automatic}
MANUAL_CELLS = {f.key: f.cell for f in FIELD_DEFINITIONS if not f.automatic}
LABELS = {f.key: f.label for f in FIELD_DEFINITIONS if f.automatic}
