"""Apply company-specific display conventions after extraction."""

import re


def normalize_origin(value: str) -> str:
    """Use confirmed domestic port abbreviations; leave unknown ports unchanged."""
    text = value.strip()
    if re.search(r"^(?:QINGDAO|QINDAO|青岛|青島)", text, re.I):
        return "QD"
    if re.search(r"^(?:TIANJIN|天津)", text, re.I):
        return "TJ"
    if re.search(r"^(?:CNNSA|NANSHA|南沙)", text, re.I):
        return "NS"
    if re.search(r"^(?:NINGBO|宁波)", text, re.I):
        return "NB"
    if re.search(r"^(?:LIANYUNGANG|连云港|連雲港)", text, re.I):
        return "LYG"
    return text
