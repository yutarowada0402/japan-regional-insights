"""Pure transformation helpers shared by ingestion, processing and tests.

These functions contain the small, testable pieces of business logic:
prefecture-code normalisation, unit conversion and derived-rate maths.
Database-side modelling (Silver/Gold) lives in the dbt project; the formulas
here mirror the dbt Gold model so both can be cross-checked.
"""

from __future__ import annotations

import re

# e-Stat area codes are 5 digits: 2-digit prefecture code + '000'.
# The national total is '00000' and is not a prefecture.
NATIONAL_AREA_CODE = "00000"

_AGE_GROUP_MAP = {
    "総数": "total",
    "65歳以上": "elderly_65plus",
}


def normalize_prefecture_code(area_code: str) -> str | None:
    """Convert an e-Stat area code ('01000') to a prefecture code ('01').

    Returns ``None`` for the national total ('00000') and raises
    ``ValueError`` for malformed codes.
    """
    code = str(area_code).strip()
    if code == NATIONAL_AREA_CODE:
        return None
    if not re.fullmatch(r"\d{5}", code) or not code.endswith("000"):
        raise ValueError(f"Unexpected e-Stat area code: {area_code!r}")
    prefecture = code[:2]
    if not ("01" <= prefecture <= "47"):
        raise ValueError(f"Prefecture code out of range: {area_code!r}")
    return prefecture


def map_age_group(name: str) -> str:
    """Map a Japanese age-group label to a stable indicator group code."""
    key = str(name).strip()
    if key not in _AGE_GROUP_MAP:
        raise ValueError(f"Unsupported age group label: {name!r}")
    return _AGE_GROUP_MAP[key]


def thousands_to_persons(value_thousands: float) -> float:
    """Convert a population value expressed in thousands to persons."""
    return float(value_thousands) * 1000.0


def population_change_rate(current: float, previous: float) -> float | None:
    """Year-on-year population change rate in percent.

    Returns ``None`` when the previous value is missing or zero, because a
    rate cannot be defined; callers must not fabricate a value.
    """
    if previous is None or previous == 0 or current is None:
        return None
    return (float(current) - float(previous)) / float(previous) * 100.0


def aging_rate(elderly: float, total: float) -> float | None:
    """Share of population aged 65+ in percent; ``None`` if undefined."""
    if total is None or total == 0 or elderly is None:
        return None
    return float(elderly) / float(total) * 100.0


def parse_year_from_time_name(time_name: str) -> int:
    """Extract the 4-digit year from an e-Stat time label like '2021年10月1日現在'."""
    match = re.search(r"(19|20)\d{2}", str(time_name))
    if not match:
        raise ValueError(f"Cannot parse year from time label: {time_name!r}")
    return int(match.group(0))
