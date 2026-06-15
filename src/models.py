from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class Job:
    source: str
    title: str
    company: str
    description: str
    url: str
    location_raw: str
    fetched_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    job_id: str | None = None
    source_country: str | None = None
    external_id: str | None = None
    search_query: str | None = None
    canonical_role: str | None = None
    country_code: str | None = None
    country_name: str | None = None
    city: str | None = None
    region: str | None = None
    remote_type: str = "unknown"
    remote_countries: list[str] = field(default_factory=list)
    language: str | None = None
    created_at: datetime | None = None
    salary_min: float | None = None
    salary_max: float | None = None
    salary_currency: str | None = None
    salary_period: str | None = "unknown"
    annual_salary_min_local: float | None = None
    annual_salary_max_local: float | None = None
    match_score: int = 0
    match_reasons: list[str] = field(default_factory=list)
    employer_authorisation: str = "unknown"
    employer_evidence: str = ""
    vacancy_authorisation_signal: str = "not_mentioned"
    vacancy_evidence: str = ""
    permit_route: str = ""
    work_authorisation_result: str = "unknown"
    eligibility_score: int = 0
    overall_score: int = 0
    alternate_urls: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        for key in ("created_at", "fetched_at"):
            if value[key] is not None:
                value[key] = value[key].isoformat()
        return value
