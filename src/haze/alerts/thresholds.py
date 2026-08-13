"""PM2.5 -> air-quality category mapping and alert thresholds.

Breakpoints follow the US EPA PM2.5 AQI categories, which are the most widely
recognised internationally and map cleanly to colour coding. They are held here
as data so they can be made country-specific later (Malaysia's API and
Indonesia's ISPU use different cut-points) without touching calling code.
"""

from __future__ import annotations

from dataclasses import dataclass

# Category boundaries in ug/m3. Upper bound is inclusive.
CATEGORIES: tuple[tuple[str, float], ...] = (
    ("GOOD", 12.0),
    ("MODERATE", 35.4),
    ("UNHEALTHY_SENSITIVE", 55.4),
    ("UNHEALTHY", 150.4),
    ("VERY_UNHEALTHY", 250.4),
    ("HAZARDOUS", float("inf")),
)

CATEGORY_ORDER: tuple[str, ...] = tuple(name for name, _ in CATEGORIES)
CATEGORY_RANK: dict[str, int] = {name: i for i, name in enumerate(CATEGORY_ORDER)}

# An institution is alerted when the forecast is expected to reach at least
# this category.
DEFAULT_ALERT_CATEGORY = "UNHEALTHY_SENSITIVE"

# Institutions serving more vulnerable populations trigger earlier, at a
# fraction of the category floor. A full tier earlier would put hospitals at
# 12.1 ug/m3, below the region's ordinary baseline of ~18 - the alert would
# never clear and would carry no information. 0.8 buys meaningful extra lead
# time while still sitting above background.
SENSITIVITY_FACTOR_BY_TYPE = {
    "school": 1.0,
    "hospital": 0.8,
    "authority": 1.0,
}

# US AQI index breakpoints, paired with CATEGORIES above, for the numeric aqi_us field.
_AQI_BREAKPOINTS: tuple[tuple[float, float, float, float], ...] = (
    (0.0, 12.0, 0, 50),
    (12.1, 35.4, 51, 100),
    (35.5, 55.4, 101, 150),
    (55.5, 150.4, 151, 200),
    (150.5, 250.4, 201, 300),
    (250.5, 500.4, 301, 500),
)


@dataclass(frozen=True)
class Threshold:
    category: str
    pm25: float


def categorise(pm25: float) -> str:
    """Return the AQI category name for a PM2.5 concentration in ug/m3."""
    for name, upper in CATEGORIES:
        if pm25 <= upper:
            return name
    return "HAZARDOUS"


def category_floor(category: str) -> float:
    """Lowest PM2.5 concentration that falls in `category`."""
    idx = CATEGORY_RANK[category]
    if idx == 0:
        return 0.0
    # Just above the previous category's upper bound.
    return round(CATEGORIES[idx - 1][1] + 0.1, 1)


def alert_threshold(institution_type: str) -> Threshold:
    """The PM2.5 level at which this kind of institution should be alerted."""
    factor = SENSITIVITY_FACTOR_BY_TYPE.get(institution_type, 1.0)
    pm25 = round(category_floor(DEFAULT_ALERT_CATEGORY) * factor, 1)
    return Threshold(category=DEFAULT_ALERT_CATEGORY, pm25=pm25)


def aqi_us(pm25: float) -> int:
    """Numeric US AQI value, linearly interpolated within the breakpoint band."""
    pm = max(0.0, min(pm25, 500.4))
    for c_lo, c_hi, i_lo, i_hi in _AQI_BREAKPOINTS:
        if pm <= c_hi:
            return round((i_hi - i_lo) / (c_hi - c_lo) * (pm - c_lo) + i_lo)
    return 500


def is_at_least(category: str, minimum: str) -> bool:
    """True if `category` is as severe as `minimum` or worse."""
    return CATEGORY_RANK[category] >= CATEGORY_RANK[minimum]
