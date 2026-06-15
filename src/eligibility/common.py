from __future__ import annotations

import json
import logging
import time

import requests

from src.config import AppConfig, DATA_DIR
from src.eligibility.base import EligibilityResult
from src.eligibility.germany import GermanyChecker
from src.eligibility.ireland import IrelandChecker
from src.eligibility.netherlands import NetherlandsChecker, download_nl_register
from src.eligibility.uk import UkChecker, download_uk_register
from src.eligibility.utils import Registry, detect_vacancy_signal
from src.models import Job

LOGGER = logging.getLogger(__name__)


def load_cached_registry(
    name: str,
    ttl_hours: float,
    loader,
) -> Registry:
    path = DATA_DIR / f"{name}_register_cache.json"
    if path.exists() and time.time() - path.stat().st_mtime < ttl_hours * 3600:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            return Registry(set(payload.get("companies", [])))
        except (OSError, ValueError):
            LOGGER.warning("registry=%s cache_invalid", name)
    try:
        companies = loader()
    except (requests.RequestException, ValueError, OSError) as exc:
        LOGGER.warning("registry=%s load_failed=%s", name, exc)
        return Registry()
    if companies:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"companies": sorted(companies)}), encoding="utf-8")
    return Registry(companies)


class EligibilityEngine:
    def __init__(
        self,
        config: AppConfig,
        *,
        uk_registry: Registry | None = None,
        nl_registry: Registry | None = None,
        countries_needed: set[str] | None = None,
    ) -> None:
        rules = config.eligibility_rules
        positive = list(rules.get("positive_terms", []))
        negative = list(rules.get("negative_terms", []))
        ttl = float(config.data.get("eligibility", {}).get("registry_cache_ttl_hours", 168))
        needed = countries_needed or {"gb", "de", "nl", "ie"}
        self.uk_registry = uk_registry or (
            load_cached_registry("uk", ttl, lambda: download_uk_register(config))
            if "gb" in needed else Registry()
        )
        self.nl_registry = nl_registry or (
            load_cached_registry("nl", ttl, lambda: download_nl_register(config))
            if "nl" in needed else Registry()
        )
        self.checkers = {
            "gb": UkChecker(self.uk_registry, positive, negative),
            "de": GermanyChecker(positive, negative),
            "nl": NetherlandsChecker(self.nl_registry, positive, negative),
            "ie": IrelandChecker(
                positive,
                negative,
                set(rules.get("ireland_critical_skills_occupations", [])),
            ),
        }

    def enrich(self, job: Job) -> Job:
        checker = self.checkers.get(job.country_code or "")
        result = checker.check(job) if checker else EligibilityResult(
            "unknown",
            "Country is unknown or outside Phase One",
            *detect_vacancy_signal(
                job,
                self.checkers["gb"].positive_terms,
                self.checkers["gb"].negative_terms,
            ),
            "",
            "unknown",
            25,
        )
        job.employer_authorisation = result.employer_authorisation
        job.employer_evidence = result.employer_evidence
        job.vacancy_authorisation_signal = result.vacancy_authorisation_signal
        job.vacancy_evidence = result.vacancy_evidence
        job.permit_route = result.permit_route
        job.work_authorisation_result = result.work_authorisation_result
        job.eligibility_score = result.eligibility_score
        return job
