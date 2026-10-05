"""Typed internal results; dictionary serialization preserves the public API."""

from dataclasses import asdict, dataclass
from typing import Callable


ProgressCallback = Callable[[str, str], None]


@dataclass
class Document:
    name: str
    role: str
    data: bytes
    text: str = ""
    read_warning: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class FieldResult:
    value: str = ""
    raw_value: str = ""
    evidence: str = ""
    source: str = ""
    source_label: str = ""
    review_reason: str = ""
    conflict: bool = False
    identifier_kind: str = ""

    @classmethod
    def from_dict(cls, entry: dict) -> "FieldResult":
        values = {key: entry[key] for key in cls.__dataclass_fields__ if key in entry}
        values.setdefault("raw_value", str(entry.get("value", "")))
        return cls(**values)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ExtractionResult:
    fields: dict[str, dict]
    mode: str
    warnings: list[str]
    documents: list[dict]

    def to_dict(self) -> dict:
        return asdict(self)
