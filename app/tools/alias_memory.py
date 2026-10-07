"""Store approved label and container-format rules without shipment values."""

import json
import os
import re
import tempfile
import threading

from app.state import FIELDS, PROJECT_ROOT, STATE_DIR
from app.security import CURRENT_USER


# The tracked file contains only reviewed seed labels. User changes stay local.
DEFAULT_FILE = PROJECT_ROOT / "data" / "field_aliases.json"
MEMORY_FILE = STATE_DIR / "approved_memory.json"


def _memory_path():
    user_id = CURRENT_USER.get()
    return STATE_DIR / "users" / str(user_id) / "approved_memory.json" if user_id is not None else MEMORY_FILE
FORMAT_OPTIONS = {"20DV": "20GP", "20DC": "20GP", "40HC": "40HQ"}
_LABEL_HINT = re.compile(
    r"提单|订舱|船名|航次|船期|箱|柜|场站|目的港|目地港|装货港|起运港|卸货港|提箱|提柜|入货|港口|"
    r"B/L|D/R|\bNO\.?\b|NUMBER|BOOKING|VESSEL|VOY|VSL|ETD|POD|POL|PORT|DEPOT|YARD|"
    r"RECEIPT|DELIVERY|QUANTITY|SIZE|TYPE|SAILING|DESTINATION|LOADING|DISCHARGE|CONTAINER|STATION",
    re.I,
)
_LOCK = threading.RLock()


def _read(path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    if not isinstance(data, dict):
        raise ValueError("字段记忆文件格式无效")
    return data


def _empty() -> dict:
    return {"aliases": {field: [] for field in FIELDS}, "disabled": {field: [] for field in FIELDS}, "formats": []}


def _local() -> dict:
    raw = _read(_memory_path())
    if "aliases" not in raw and any(field in raw for field in FIELDS):
        raw = {"aliases": raw}
    state = _empty()
    for group in ("aliases", "disabled"):
        values = raw.get(group, {})
        if isinstance(values, dict):
            for field in FIELDS:
                if isinstance(values.get(field), list):
                    state[group][field] = [value for value in values[field] if isinstance(value, str)]
    formats = raw.get("formats", [])
    if isinstance(formats, list):
        state["formats"] = [source for source in formats if source in FORMAT_OPTIONS]
    return state


def _save(state: dict) -> None:
    path = _memory_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                     suffix=".json", delete=False) as temporary_file:
        json.dump({"aliases": {field: values for field, values in state["aliases"].items() if values},
                   "disabled": {field: values for field, values in state["disabled"].items() if values},
                   "formats": state["formats"]}, temporary_file, ensure_ascii=False, indent=2)
        temporary_file.write("\n")
        temporary_path = temporary_file.name
    try:
        os.replace(temporary_path, path)
    finally:
        if os.path.exists(temporary_path):
            os.unlink(temporary_path)


def _valid_label(label: str) -> bool:
    return (2 <= len(label) <= 60
            and bool(re.search(r"[A-Za-z\u4e00-\u9fff]{2,}", label))
            and bool(_LABEL_HINT.search(label))
            and not re.search(r"https?://|@|\d{4,}|[\r\n]", label, re.I))


def load_aliases() -> dict[str, list[str]]:
    with _LOCK:
        defaults = _read(DEFAULT_FILE)
        state = _local()
        result = {}
        for field in FIELDS:
            seen = set()
            disabled = {value.casefold() for value in state["disabled"][field]}
            result[field] = []
            seed = defaults.get(field, [])
            for value in (seed if isinstance(seed, list) else []) + state["aliases"][field]:
                if isinstance(value, str) and _valid_label(value) and value.casefold() not in seen | disabled:
                    result[field].append(value)
                    seen.add(value.casefold())
        return result


def list_memory() -> dict:
    with _LOCK:
        aliases = load_aliases()
        state = _local()
        return {"aliases": aliases,
                "formats": [{"source": source, "target": FORMAT_OPTIONS[source]} for source in state["formats"]],
                "format_options": [{"source": source, "target": target} for source, target in FORMAT_OPTIONS.items()]}


def remember_aliases(candidates: list[dict]) -> int:
    """Save only labels explicitly selected during human review."""
    if not isinstance(candidates, list):
        return 0
    with _LOCK:
        state = _local()
        aliases = load_aliases()
        added = 0
        for candidate in candidates[:len(FIELDS)]:
            if not isinstance(candidate, dict):
                continue
            field = candidate.get("field")
            label = re.sub(r"\s+", " ", str(candidate.get("source_label", ""))).strip(" :：")
            if field not in FIELDS or not _valid_label(label):
                continue
            folded = label.casefold()
            if any(folded in {known.casefold() for known in aliases[other]}
                   for other in FIELDS if other != field):
                continue
            if folded in {known.casefold() for known in aliases[field]}:
                continue
            state["disabled"][field] = [item for item in state["disabled"][field] if item.casefold() != folded]
            if folded not in {item.casefold() for item in state["aliases"][field]}:
                state["aliases"][field].append(label)
            aliases[field].append(label)
            added += 1
        if added:
            _save(state)
        return added


def remove_alias(field: str, label: str) -> bool:
    """Hide a seed label or delete a locally approved label; both can be restored."""
    if field not in FIELDS or not isinstance(label, str):
        raise ValueError("字段或标签无效")
    with _LOCK:
        if label.casefold() not in {item.casefold() for item in load_aliases()[field]}:
            return False
        state = _local()
        state["aliases"][field] = [item for item in state["aliases"][field] if item.casefold() != label.casefold()]
        if label.casefold() not in {item.casefold() for item in state["disabled"][field]}:
            state["disabled"][field].append(label)
        _save(state)
        return True


def add_format_rule(source: str) -> bool:
    if source not in FORMAT_OPTIONS:
        raise ValueError("只允许审核过的箱型格式规则")
    with _LOCK:
        state = _local()
        if source in state["formats"]:
            return False
        state["formats"].append(source)
        _save(state)
        return True


def remove_format_rule(source: str) -> bool:
    if source not in FORMAT_OPTIONS:
        raise ValueError("箱型格式规则无效")
    with _LOCK:
        state = _local()
        if source not in state["formats"]:
            return False
        state["formats"].remove(source)
        _save(state)
        return True


def apply_format_rules(value: str) -> str:
    with _LOCK:
        sources = _local()["formats"]
    for source in sources:
        value = re.sub(rf"(?i)(?<=X){re.escape(source)}\b", FORMAT_OPTIONS[source], value)
    return value
