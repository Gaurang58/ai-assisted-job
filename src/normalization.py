from __future__ import annotations

import re
from datetime import datetime
from html import unescape
from typing import Any

COUNTRY_NAMES = {
    "gb": "United Kingdom",
    "de": "Germany",
    "nl": "Netherlands",
    "ie": "Ireland",
}
COUNTRY_CURRENCIES = {"gb": "GBP", "de": "EUR", "nl": "EUR", "ie": "EUR"}
CITY_COUNTRIES = {
    "london": ("gb", "London"),
    "manchester": ("gb", "Manchester"),
    "birmingham": ("gb", "Birmingham"),
    "leeds": ("gb", "Leeds"),
    "bristol": ("gb", "Bristol"),
    "berlin": ("de", "Berlin"),
    "munich": ("de", "Munich"),
    "münchen": ("de", "Munich"),
    "hamburg": ("de", "Hamburg"),
    "frankfurt": ("de", "Frankfurt"),
    "amsterdam": ("nl", "Amsterdam"),
    "rotterdam": ("nl", "Rotterdam"),
    "utrecht": ("nl", "Utrecht"),
    "eindhoven": ("nl", "Eindhoven"),
    "dublin": ("ie", "Dublin"),
    "cork": ("ie", "Cork"),
    "galway": ("ie", "Galway"),
    "limerick": ("ie", "Limerick"),
}
COUNTRY_ALIASES = {
    "gb": ["united kingdom", "england", "scotland", "wales", " uk"],
    "de": ["germany", "deutschland"],
    "nl": ["netherlands", "nederland"],
    "ie": ["republic of ireland", "ireland"],
}
REMOTE_TYPES = {"onsite", "hybrid", "remote", "remote_country_restricted", "unknown"}
SALARY_PERIODS = {"annual", "monthly", "weekly", "daily", "hourly", "unknown"}
ANNUAL_FACTORS = {"annual": 1, "monthly": 12, "weekly": 52, "daily": 260, "hourly": 2080}


def strip_html(value: str) -> str:
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", value or ""))).strip()


def parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if not value:
        return None
    text = str(value).strip().replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _contains(text: str, phrase: str) -> bool:
    return bool(re.search(rf"(?<!\w){re.escape(phrase)}(?!\w)", text, re.IGNORECASE))


def normalize_location(
    location_raw: str,
    structured_country: str | None = None,
    remote_hint: bool | None = None,
) -> tuple[str | None, str | None, str | None, str]:
    text = (location_raw or "").strip()
    lowered = f" {text.lower()} "
    country = structured_country.lower() if structured_country else None
    if country not in COUNTRY_NAMES:
        country = None
    city = None
    for alias, (city_country, canonical_city) in CITY_COUNTRIES.items():
        if _contains(lowered, alias):
            city = canonical_city
            country = country or city_country
            break
    if country is None:
        for code, aliases in COUNTRY_ALIASES.items():
            if any(_contains(lowered, alias.strip()) for alias in aliases):
                country = code
                break

    has_remote = remote_hint is True or _contains(lowered, "remote")
    has_hybrid = _contains(lowered, "hybrid")
    if has_hybrid:
        remote_type = "hybrid"
    elif has_remote and country:
        remote_type = "remote_country_restricted"
    elif has_remote:
        remote_type = "remote"
    elif text:
        remote_type = "onsite"
    else:
        remote_type = "unknown"
    return country, COUNTRY_NAMES.get(country), city, remote_type


def normalize_salary(
    salary_min: Any,
    salary_max: Any,
    currency: str | None,
    period: str | None,
    country_code: str | None,
) -> tuple[float | None, float | None, str | None, str, float | None, float | None]:
    def number(value: Any) -> float | None:
        try:
            return float(value) if value not in (None, "") else None
        except (TypeError, ValueError):
            return None

    low, high = number(salary_min), number(salary_max)
    normalized_period = (period or "unknown").lower()
    if normalized_period not in SALARY_PERIODS:
        normalized_period = "unknown"
    normalized_currency = currency.upper() if currency else COUNTRY_CURRENCIES.get(country_code or "")
    factor = ANNUAL_FACTORS.get(normalized_period)
    annual_low = low * factor if low is not None and factor else None
    annual_high = high * factor if high is not None and factor else None
    return low, high, normalized_currency, normalized_period, annual_low, annual_high
