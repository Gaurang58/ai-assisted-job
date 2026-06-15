from __future__ import annotations

import logging
import os
from typing import Any

import requests

from src.config import AppConfig
from src.models import Job
from src.normalization import normalize_location, normalize_salary, parse_datetime, strip_html
from src.providers.base import request_json, retrying_session

LOGGER = logging.getLogger(__name__)
ENDPOINT = "https://www.reed.co.uk/api/1.0/search"


def normalize_reed_job(item: dict[str, Any], query: str, location: str) -> Job:
    location_raw = str(item.get("locationName") or location or "")
    country_code, country_name, city, remote_type = normalize_location(location_raw, "gb")
    salary = normalize_salary(
        item.get("minimumSalary") or item.get("yearlyMinimumSalary"),
        item.get("maximumSalary") or item.get("yearlyMaximumSalary"),
        item.get("currency") or "GBP",
        "annual",
        "gb",
    )
    return Job(
        source="reed",
        source_country="gb",
        external_id=str(item.get("jobId") or "") or None,
        search_query=query,
        title=str(item.get("jobTitle") or "").strip(),
        company=str(item.get("employerName") or "Unknown").strip(),
        description=strip_html(str(item.get("jobDescription") or item.get("description") or "")),
        url=str(item.get("jobUrl") or item.get("externalUrl") or ""),
        location_raw=location_raw,
        country_code=country_code,
        country_name=country_name,
        city=city,
        remote_type=remote_type,
        created_at=parse_datetime(item.get("date") or item.get("expirationDate")),
        salary_min=salary[0],
        salary_max=salary[1],
        salary_currency=salary[2],
        salary_period=salary[3],
        annual_salary_min_local=salary[4],
        annual_salary_max_local=salary[5],
    )


class ReedProvider:
    name = "reed"

    def __init__(self, session: requests.Session | None = None) -> None:
        self.session = session or retrying_session()

    def fetch(self, config: AppConfig) -> list[Job]:
        settings = config.provider(self.name)
        api_key = os.getenv("REED_API_KEY")
        if not settings.get("enabled", True) or not api_key or "gb" not in config.countries:
            return []
        jobs: list[Job] = []
        locations = config.data["search"].get("reed_locations", ["London"])
        count = min(int(config.data["search"].get("results_per_query", 40)), 100)
        for query in config.queries:
            for location in locations:
                try:
                    payload = request_json(
                        self.session,
                        ENDPOINT,
                        params={"keywords": query, "locationName": location, "resultsToTake": count},
                        auth=(api_key, ""),
                    )
                    rows = payload.get("results", [])
                    jobs.extend(normalize_reed_job(item, query, location) for item in rows)
                    LOGGER.info("provider=reed country=gb query=%r raw_count=%d", query, len(rows))
                except (requests.RequestException, ValueError) as exc:
                    LOGGER.warning("provider=reed country=gb query=%r failed=%s", query, exc)
        return jobs
