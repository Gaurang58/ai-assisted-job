from __future__ import annotations

import logging
import os
import time
from typing import Any

import requests

from src.config import AppConfig
from src.models import Job
from src.normalization import normalize_location, normalize_salary, parse_datetime, strip_html
from src.providers.base import request_json, retrying_session

LOGGER = logging.getLogger(__name__)
ENDPOINT = "https://api.adzuna.com/v1/api/jobs/{country}/search/1"


def normalize_adzuna_job(item: dict[str, Any], country: str, query: str) -> Job:
    company = item.get("company") or {}
    location = item.get("location") or {}
    location_raw = str(location.get("display_name") or "")
    country_code, country_name, city, remote_type = normalize_location(location_raw, country)
    salary = normalize_salary(
        item.get("salary_min"),
        item.get("salary_max"),
        item.get("salary_currency") or item.get("currency"),
        item.get("salary_period") or "annual",
        country_code,
    )
    return Job(
        source="adzuna",
        source_country=country,
        external_id=str(item.get("id") or "") or None,
        search_query=query,
        title=str(item.get("title") or "").strip(),
        company=str(company.get("display_name") or "Unknown").strip(),
        description=strip_html(str(item.get("description") or "")),
        url=str(item.get("redirect_url") or ""),
        location_raw=location_raw,
        country_code=country_code,
        country_name=country_name,
        city=city,
        remote_type=remote_type,
        created_at=parse_datetime(item.get("created")),
        salary_min=salary[0],
        salary_max=salary[1],
        salary_currency=salary[2],
        salary_period=salary[3],
        annual_salary_min_local=salary[4],
        annual_salary_max_local=salary[5],
    )


class AdzunaProvider:
    name = "adzuna"

    def __init__(self, session: requests.Session | None = None) -> None:
        self.session = session or retrying_session()

    def fetch(self, config: AppConfig) -> list[Job]:
        settings = config.provider(self.name)
        if not settings.get("enabled", True):
            return []
        app_id, app_key = os.getenv("ADZUNA_APP_ID"), os.getenv("ADZUNA_APP_KEY")
        if not app_id or not app_key:
            LOGGER.warning("provider=adzuna skipped: ADZUNA credentials are missing")
            return []
        jobs: list[Job] = []
        countries = [c for c in settings.get("countries", config.countries) if c in config.countries]
        delay = float(settings.get("request_delay_seconds", 0.2))
        count = int(config.data["search"].get("results_per_query", 40))
        for country in countries:
            for query in config.queries:
                try:
                    payload = request_json(
                        self.session,
                        ENDPOINT.format(country=country),
                        params={
                            "app_id": app_id,
                            "app_key": app_key,
                            "what": query,
                            "results_per_page": count,
                            "sort_by": "date",
                            "content-type": "application/json",
                        },
                    )
                    rows = payload.get("results", [])
                    jobs.extend(normalize_adzuna_job(item, country, query) for item in rows)
                    LOGGER.info("provider=adzuna country=%s query=%r raw_count=%d", country, query, len(rows))
                except (requests.RequestException, ValueError) as exc:
                    LOGGER.warning(
                        "provider=adzuna country=%s query=%r failed=%s", country, query, exc
                    )
                if delay:
                    time.sleep(delay)
        return jobs
