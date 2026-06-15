"""Provider orchestration and compatibility exports."""

from __future__ import annotations

import logging
from collections import Counter

from src.config import AppConfig
from src.models import Job
from src.providers import (
    AdzunaProvider,
    ArbeitnowProvider,
    JobicyProvider,
    ReedProvider,
    RssProvider,
)
from src.providers.adzuna import normalize_adzuna_job
from src.providers.reed import normalize_reed_job
from src.providers.rss import normalize_rss_job

LOGGER = logging.getLogger(__name__)
DEFAULT_PROVIDERS = (
    AdzunaProvider,
    ReedProvider,
    RssProvider,
    ArbeitnowProvider,
    JobicyProvider,
)


def fetch_jobs(config: AppConfig, providers=None) -> list[Job]:
    jobs: list[Job] = []
    for provider in providers or [factory() for factory in DEFAULT_PROVIDERS]:
        try:
            fetched = provider.fetch(config)
            jobs.extend(fetched)
            LOGGER.info("provider=%s normalised_count=%d", provider.name, len(fetched))
        except Exception as exc:
            LOGGER.exception("provider=%s isolated_failure=%s", provider.name, exc)
    return jobs


def count_by_provider(jobs: list[Job]) -> dict[str, int]:
    return dict(Counter(job.source for job in jobs))


def count_by_country(jobs: list[Job]) -> dict[str, int]:
    return dict(Counter(job.country_code or "unknown" for job in jobs))
