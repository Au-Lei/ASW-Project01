"""Apply company-specific display conventions after extraction."""

import re


def normalize_origin(value: str) -> str:
    """Use confirmed domestic port abbreviations; leave unknown ports unchanged."""
    text = value.strip()
    if re.search(r"^(?:QINGDAO|QINDAO|青岛|青島)", text, re.I):
        return "QD"
    if re.search(r"^(?:TIANJIN|天津)", text, re.I):
        return "TJ"
    return text
