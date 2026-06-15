from __future__ import annotations

from src.eligibility.base import EligibilityResult
from src.eligibility.utils import detect_vacancy_signal
from src.models import Job


class GermanyChecker:
    def __init__(self, positive_terms: list[str], negative_terms: list[str]):
        self.positive_terms = positive_terms
        self.negative_terms = negative_terms

    def check(self, job: Job) -> EligibilityResult:
        signal, evidence = detect_vacancy_signal(job, self.positive_terms, self.negative_terms)
        text = f"{job.title} {job.description}".lower()
        route = "de_eu_blue_card" if "blue card" in text else (
            "de_skilled_worker" if signal == "explicit_positive" else ""
        )
        if signal == "explicit_negative":
            result, score = "unlikely", 0
        elif signal == "explicit_positive":
            result, score = "possible", 75
        else:
            result, score = "unknown", 35
        return EligibilityResult(
            "not_register_based",
            "Germany is assessed from vacancy and permit-route evidence, not an employer register",
            signal,
            evidence,
            route,
            result,
            score,
        )
