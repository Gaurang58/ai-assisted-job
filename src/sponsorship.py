"""Compatibility helpers for the former sponsorship module."""

from src.eligibility.common import EligibilityEngine
from src.eligibility.utils import Registry, normalize_company

RECRUITER_WORDS = {
    "recruitment", "recruiter", "staffing", "talent", "resourcing",
    "consulting", "consultancy", "agency",
}


def is_recruiter_company(company: str) -> bool:
    lowered = (company or "").lower()
    return any(word in lowered for word in RECRUITER_WORDS)


__all__ = ["EligibilityEngine", "Registry", "normalize_company", "is_recruiter_company"]
