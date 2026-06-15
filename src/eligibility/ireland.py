from __future__ import annotations

from src.eligibility.base import EligibilityResult
from src.eligibility.utils import detect_vacancy_signal
from src.models import Job


class IrelandChecker:
    def __init__(
        self,
        positive_terms: list[str],
        negative_terms: list[str],
        critical_occupations: set[str],
    ):
        self.positive_terms = positive_terms
        self.negative_terms = negative_terms
        self.critical_occupations = {value.lower() for value in critical_occupations}

    def check(self, job: Job) -> EligibilityResult:
        signal, evidence = detect_vacancy_signal(job, self.positive_terms, self.negative_terms)
        critical = (job.canonical_role or "").lower() in self.critical_occupations or any(
            occupation in job.title.lower() for occupation in self.critical_occupations
        )
        text = f"{job.title} {job.description}".lower()
        route = (
            "ie_critical_skills"
            if critical or "critical skills" in text
            else "ie_general_employment_permit"
            if signal == "explicit_positive"
            else ""
        )
        if signal == "explicit_negative":
            result, score = "unlikely", 0
        elif signal == "explicit_positive" and critical:
            result, score = "strong", 90
        elif signal == "explicit_positive" or critical:
            result, score = "possible", 65
        else:
            result, score = "unknown", 30
        return EligibilityResult(
            "not_register_based",
            "Ireland is assessed from vacancy wording and configured occupation evidence",
            signal,
            evidence,
            route,
            result,
            score,
        )
