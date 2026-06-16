from __future__ import annotations

import logging
import os
import time
from typing import Any

import requests

from src.config import AppConfig
from src.models import Job
from src.normalization import COUNTRY_NAMES, normalize_location, normalize_salary, strip_html
from src.providers.base import request_json, retrying_session

LOGGER = logging.getLogger(__name__)
ENDPOINT = "https://serpapi.com/search"
GOOGLE_DOMAINS = {
    "gb": "google.co.uk",
    "de": "google.de",
    "nl": "google.nl",
    "ie": "google.ie",
}
GL_CODES = {"gb": "uk", "de": "de", "nl": "nl", "ie": "ie"}


def _first_apply_link(item: dict[str, Any]) -> str:
    for option in item.get("apply_options") or []:
        link = option.get("link")
        if link:
            return str(link)
    return str(item.get("share_link") or "")


def normalize_serpapi_job(item: dict[str, Any], country: str, query: str) -> Job:
    detected = item.get("detected_extensions") or {}
    extensions = [str(value).lower() for value in item.get("extensions") or []]
    remote_hint = bool(detected.get("work_from_home")) or any(
        value in {"remote", "work from home"} or "work from home" in value
        for value in extensions
    )
    location_raw = str(item.get("location") or COUNTRY_NAMES.get(country) or "")
    country_code, country_name, city, remote_type = normalize_location(
        location_raw,
        country,
        remote_hint=remote_hint,
    )
    salary = normalize_salary(None, None, None, "unknown", country_code)
    return Job(
        source="serpapi",
        source_country=country,
        external_id=str(item.get("job_id") or "") or None,
        search_query=query,
        title=str(item.get("title") or "").strip(),
        company=str(item.get("company_name") or "Unknown").strip(),
        description=strip_html(str(item.get("description") or "")),
        url=_first_apply_link(item),
        location_raw=location_raw,
        country_code=country_code,
        country_name=country_name,
        city=city,
        remote_type=remote_type,
        remote_countries=[country] if remote_type == "remote_country_restricted" else [],
        salary_min=salary[0],
        salary_max=salary[1],
        salary_currency=salary[2],
        salary_period=salary[3],
        annual_salary_min_local=salary[4],
        annual_salary_max_local=salary[5],
        metadata={
            "via": item.get("via"),
            "extensions": item.get("extensions") or [],
            "detected_extensions": detected,
            "apply_options": item.get("apply_options") or [],
            "share_link": item.get("share_link"),
        },
    )


class SerpApiProvider:
    name = "serpapi"

    def __init__(self, session: requests.Session | None = None) -> None:
        self.session = session or retrying_session()

    def fetch(self, config: AppConfig) -> list[Job]:
        settings = config.provider(self.name)
        if not settings.get("enabled", False):
            return []
        api_key = os.getenv("SERPAPI_API_KEY")
        if not api_key:
            LOGGER.warning("provider=serpapi skipped: SERPAPI_API_KEY is missing")
            return []

        jobs: list[Job] = []
        countries = [
            country
            for country in settings.get("countries", config.countries)
            if country in config.countries
        ]
        delay = float(settings.get("request_delay_seconds", 0.2))
        language = str(settings.get("hl", "en"))
        locations = settings.get("locations", {})

        for country in countries:
            location = str(locations.get(country) or COUNTRY_NAMES.get(country) or country)
            for query in config.queries:
                try:
                    payload = request_json(
                        self.session,
                        ENDPOINT,
                        params={
                            "engine": "google_jobs",
                            "api_key": api_key,
                            "q": query,
                            "location": location,
                            "google_domain": GOOGLE_DOMAINS.get(country, "google.com"),
                            "gl": GL_CODES.get(country, country),
                            "hl": language,
                        },
                    )
                    rows = payload.get("jobs_results", [])
                    jobs.extend(normalize_serpapi_job(item, country, query) for item in rows)
                    LOGGER.info(
                        "provider=serpapi country=%s query=%r raw_count=%d",
                        country,
                        query,
                        len(rows),
                    )
                except (requests.RequestException, ValueError) as exc:
                    LOGGER.warning(
                        "provider=serpapi country=%s query=%r failed=%s",
                        country,
                        query,
                        exc,
                    )
                if delay:
                    time.sleep(delay)
        return jobs
