from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from src.models import Job


@dataclass(frozen=True)
class EligibilityResult:
    employer_authorisation: str
    employer_evidence: str
    vacancy_authorisation_signal: str
    vacancy_evidence: str
    permit_route: str
    work_authorisation_result: str
    eligibility_score: int


class CountryEligibilityChecker(Protocol):
    def check(self, job: Job) -> EligibilityResult: ...
