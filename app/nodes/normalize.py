"""Apply company-specific display conventions after extraction."""

import re


_MONTHS = {month: index for index, month in enumerate(
    ("JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"), 1
)}
_COUNTRIES = (
    "QATAR", "CHINA", "MALAYSIA", "INDONESIA", "INDIA", "JAPAN",
    "SOUTH KOREA", "KOREA", "THAILAND", "VIETNAM", "CANADA",
    "UNITED ARAB EMIRATES", "TURKEY", "PHILIPPINES", "BANGLADESH",
    "SINGAPORE", "AUSTRALIA", "UNITED STATES", "USA",
)


def normalize_sailing_date(value: str) -> str:
    """Display an unambiguous sailing date as month.day without leading zeroes."""
    value = value.strip()
    match = re.fullmatch(r"(\d{1,2})[ -]([A-Za-z]{3})[ -](20\d{2})", value)
    if match and match.group(2).upper() in _MONTHS:
        day = int(match.group(1))
        if 1 <= day <= 31:
            return f"{_MONTHS[match.group(2).upper()]}.{day}"
    match = re.fullmatch(r"20\d{2}[-/.](\d{1,2})[-/.](\d{1,2})", value)
    if not match:
        match = re.fullmatch(r"(\d{1,2})[-/.](\d{1,2})", value)
    if match:
        month, day = map(int, match.groups())
        if 1 <= month <= 12 and 1 <= day <= 31:
            return f"{month}.{day}"
    return value


def normalize_destination(value: str) -> str:
    """Remove only a recognizable country suffix after a port name."""
    value = value.strip()
    for country in _COUNTRIES:
        suffix = re.search(rf"[;,，；]\s*{re.escape(country)}\s*$", value, re.I)
        if suffix:
            return value[:suffix.start()].strip()
    return value


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
