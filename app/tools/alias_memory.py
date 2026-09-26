"""Persist human-approved field-label aliases without shipment values."""

import json
import os
import re
import tempfile
import threading

from app.state import FIELDS, PROJECT_ROOT


MEMORY_FILE = PROJECT_ROOT / "data" / "field_aliases.json"
_LOCK = threading.RLock()


def load_aliases() -> dict[str, list[str]]:
    with _LOCK:
        try:
            raw = json.loads(MEMORY_FILE.read_text(encoding="utf-8"))
        except FileNotFoundError:
            raw = {}
        return {field: [alias for alias in raw.get(field, []) if isinstance(alias, str)] for field in FIELDS}


def _valid_label(label: str) -> bool:
    return (
        2 <= len(label) <= 60
        and bool(re.search(r"[A-Za-z\u4e00-\u9fff]{2,}", label))
        and not re.search(r"https?://|@|\d{5,}|[\r\n]", label, re.I)
    )


def remember_aliases(candidates: list[dict]) -> int:
    """Called only after a user confirms the extracted workbook for download."""
    if not isinstance(candidates, list):
        return 0
    with _LOCK:
        aliases = load_aliases()
        added = 0
        for candidate in candidates[: len(FIELDS)]:
            if not isinstance(candidate, dict):
                continue
            field = candidate.get("field")
            label = re.sub(r"\s+", " ", str(candidate.get("source_label", ""))).strip(" :：")
            if field not in FIELDS or not _valid_label(label):
                continue
            if any(label.casefold() in {known.casefold() for known in aliases[other]} for other in FIELDS if other != field):
                continue
            if label.casefold() in {known.casefold() for known in aliases[field]}:
                continue
            aliases[field].append(label)
            added += 1
        if added:
            MEMORY_FILE.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=MEMORY_FILE.parent, suffix=".json", delete=False) as temporary_file:
                json.dump({field: values for field, values in aliases.items() if values}, temporary_file, ensure_ascii=False, indent=2)
                temporary_file.write("\n")
                temporary_path = temporary_file.name
            try:
                os.replace(temporary_path, MEMORY_FILE)
            finally:
                if os.path.exists(temporary_path):
                    os.unlink(temporary_path)
        return added
