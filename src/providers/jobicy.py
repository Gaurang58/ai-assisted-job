from __future__ import annotations

import logging
from typing import Any

import requests

from src.config import AppConfig
from src.models import Job
from src.normalization import COUNTRY_NAMES, normalize_salary, parse_datetime, strip_html
from src.providers.base import request_json, retrying_session

LOGGER = logging.getLogger(__name__)
ENDPOINT = "https://jobicy.com/api/v2/remote-jobs"
GEO_SLUGS = {"gb": "uk", "de": "germany", "nl": "netherlands", "ie": "ireland"}


def normalize_jobicy_job(item: dict[str, Any], requested_country: str) -> Job:
    period_aliases = {
        "year": "annual",
        "yearly": "annual",
        "month": "monthly",
        "week": "weekly",
        "day": "daily",
        "hour": "hourly",
    }
    raw_period = str(item.get("salaryPeriod") or "unknown").lower()
    salary = normalize_salary(
        item.get("salaryMin"),
        item.get("salaryMax"),
        item.get("salaryCurrency"),
        period_aliases.get(raw_period, raw_period),
        requested_country,
    )
    location_raw = str(item.get("jobGeo") or COUNTRY_NAMES[requested_country])
    return Job(
        source="jobicy",
        source_country=requested_country,
        external_id=str(item.get("id") or item.get("jobSlug") or "") or None,
        search_query=f"jobicy:{requested_country}",
        title=str(item.get("jobTitle") or "").strip(),
        company=str(item.get("companyName") or "Unknown").strip(),
        description=strip_html(
            str(item.get("jobDescription") or item.get("jobExcerpt") or "")
        ),
        url=str(item.get("url") or ""),
        location_raw=location_raw,
        country_code=requested_country,
        country_name=COUNTRY_NAMES[requested_country],
        remote_type="remote_country_restricted",
        remote_countries=[requested_country],
        created_at=parse_datetime(item.get("pubDate")),
        salary_min=salary[0],
        salary_max=salary[1],
        salary_currency=salary[2],
        salary_period=salary[3],
        annual_salary_min_local=salary[4],
        annual_salary_max_local=salary[5],
        metadata={
            "job_geo": item.get("jobGeo"),
            "job_level": item.get("jobLevel"),
            "job_type": item.get("jobType") or [],
            "industry": item.get("jobIndustry") or [],
        },
    )


class JobicyProvider:
    name = "jobicy"

    def __init__(self, session: requests.Session | None = None) -> None:
        self.session = session or retrying_session()

    def fetch(self, config: AppConfig) -> list[Job]:
        settings = config.provider(self.name)
        if not settings.get("enabled", True):
            return []
        jobs: list[Job] = []
        count = min(int(settings.get("results_per_request", 100)), 100)
        excluded_levels = {
            str(level).lower() for level in settings.get("excluded_levels", [])
        }
        countries = [
            country
            for country in settings.get("countries", ["ie", "nl", "de"])
            if country in config.countries
        ]
        for country in countries:
            for industry in settings.get("industries", ["engineering"]):
                try:
                    payload = request_json(
                        self.session,
                        ENDPOINT,
                        params={
                            "count": count,
                            "geo": GEO_SLUGS[country],
                            "industry": industry,
                        },
                    )
                    rows = payload.get("jobs", [])
                    jobs.extend(
                        normalize_jobicy_job(item, country)
                        for item in rows
                        if str(item.get("jobLevel") or "").lower() not in excluded_levels
                    )
                    LOGGER.info(
                        "provider=jobicy country=%s industry=%s raw_count=%d",
                        country,
                        industry,
                        len(rows),
                    )
                except (requests.RequestException, ValueError) as exc:
                    LOGGER.warning(
                        "provider=jobicy country=%s industry=%s failed=%s",
                        country,
                        industry,
                        exc,
                    )
        return jobs
