"""Apply company-specific display conventions after extraction."""

import re

from app.models import FieldResult
from app.state import FIELDS
from app.business import COUNTRY_SUFFIXES, DESTINATION_PORT_CODES, ORIGIN_ALIASES


_MONTHS = {month: index for index, month in enumerate(
    ("JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"), 1
)}


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
    """Show the overseas port, not its terminal, province, or country."""
    value = value.strip()
    value = re.split(r"\s+Terminal\b|\s*/\s*(?:Unit|Sociedad|Mersin Int'l)", value, 1, flags=re.I)[0].strip()
    value = re.sub(r"\s+PORT\s*$", "", value, flags=re.I).strip()
    value = re.sub(r"^([A-Z]{5})\s*\(\s*([^)]*)\s*\)$", r"\2", value).strip()
    for country in COUNTRY_SUFFIXES:
        suffix = re.search(rf"[;,，；]\s*{re.escape(country)}\s*$", value, re.I)
        if suffix:
            value = value[:suffix.start()].strip()
            break
    value = re.sub(r",\s*(?:SOUTH|PEOPLE|BC|QC)\s*$", "", value, flags=re.I).strip()
    value = re.sub(r",\s*([^,]+)$", lambda m: "" if m.group(1).strip().casefold() == value.split(",", 1)[0].strip().casefold() else m.group(0), value)
    value = re.sub(r"\s+PORT\s*$", "", value, flags=re.I).strip()
    return DESTINATION_PORT_CODES.get(value.upper(), value)


def normalize_origin(value: str) -> str:
    """Use confirmed domestic port abbreviations; leave unknown ports unchanged."""
    text = value.strip()
    for pattern, abbreviation in ORIGIN_ALIASES:
        if re.search(pattern, text, re.I):
            return abbreviation
    return text


def normalize_fields(fields: dict) -> dict:
    """The shared, idempotent display boundary for rule and AI results."""
    normalizers = {"origin": normalize_origin, "destination": normalize_destination,
                   "sailing_date": normalize_sailing_date}
    result = {}
    for key in FIELDS:
        entry = FieldResult.from_dict(fields.get(key, {}))
        entry.value = normalizers.get(key, str.strip)(entry.value)
        result[key] = entry.to_dict()
    return result
