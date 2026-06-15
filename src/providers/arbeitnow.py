from __future__ import annotations

import logging
from typing import Any

import requests

from src.config import AppConfig
from src.models import Job
from src.normalization import normalize_location, normalize_salary, parse_datetime, strip_html
from src.providers.base import request_json, retrying_session

LOGGER = logging.getLogger(__name__)
ENDPOINT = "https://www.arbeitnow.com/api/job-board-api"


def normalize_arbeitnow_job(item: dict[str, Any]) -> Job:
    location_raw = str(item.get("location") or "")
    country_code, country_name, city, remote_type = normalize_location(
        location_raw, remote_hint=bool(item.get("remote"))
    )
    salary = normalize_salary(
        item.get("salary_min"),
        item.get("salary_max"),
        item.get("currency"),
        item.get("salary_period") or "unknown",
        country_code,
    )
    description = strip_html(str(item.get("description") or ""))
    if item.get("visa_sponsorship"):
        description = f"{description} Visa sponsorship available."
    return Job(
        source="arbeitnow",
        source_country=country_code,
        external_id=str(item.get("slug") or item.get("id") or "") or None,
        search_query="arbeitnow",
        title=str(item.get("title") or "").strip(),
        company=str(item.get("company_name") or "Unknown").strip(),
        description=description,
        url=str(item.get("url") or ""),
        location_raw=location_raw,
        country_code=country_code,
        country_name=country_name,
        city=city,
        remote_type=remote_type,
        remote_countries=[country_code] if remote_type == "remote_country_restricted" and country_code else [],
        created_at=parse_datetime(item.get("created_at")),
        salary_min=salary[0],
        salary_max=salary[1],
        salary_currency=salary[2],
        salary_period=salary[3],
        annual_salary_min_local=salary[4],
        annual_salary_max_local=salary[5],
        metadata={"tags": item.get("tags") or [], "visa_sponsorship": item.get("visa_sponsorship")},
    )


class ArbeitnowProvider:
    name = "arbeitnow"

    def __init__(self, session: requests.Session | None = None) -> None:
        self.session = session or retrying_session()

    def fetch(self, config: AppConfig) -> list[Job]:
        if not config.provider(self.name).get("enabled", True):
            return []
        try:
            payload = request_json(self.session, ENDPOINT)
            rows = payload.get("data", [])
            jobs = [normalize_arbeitnow_job(item) for item in rows]
            jobs = [job for job in jobs if job.country_code in config.countries or job.country_code is None]
            LOGGER.info("provider=arbeitnow raw_count=%d normalised_count=%d", len(rows), len(jobs))
            return jobs
        except (requests.RequestException, ValueError) as exc:
            LOGGER.warning("provider=arbeitnow failed=%s", exc)
            return []
