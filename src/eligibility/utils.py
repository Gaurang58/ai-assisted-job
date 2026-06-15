from __future__ import annotations

import re

from src.models import Job


def clean(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").lower()).strip()


def detect_vacancy_signal(
    job: Job, positive_terms: list[str], negative_terms: list[str]
) -> tuple[str, str]:
    text = clean(f"{job.title} {job.description}")
    for phrase in negative_terms:
        if clean(phrase) in text:
            return "explicit_negative", f'Vacancy says "{phrase}"'
    for phrase in positive_terms:
        if clean(phrase) in text:
            return "explicit_positive", f'Vacancy says "{phrase}"'
    if "sponsor" in text or "visa" in text or "work permit" in text:
        return "ambiguous", "Vacancy mentions work authorisation without a clear commitment"
    return "not_mentioned", "No explicit work-authorisation wording found"


def normalize_company(value: str) -> str:
    text = re.sub(r"[^\w\s]", " ", clean(value))
    suffixes = {"ltd", "limited", "plc", "llp", "llc", "inc", "group", "bv", "gmbh"}
    return " ".join(word for word in text.split() if word not in suffixes)


class Registry:
    def __init__(self, names: set[str] | None = None) -> None:
        self.index = {normalize_company(name): name for name in (names or set()) if name}

    def match(self, company: str) -> str | None:
        normalized = normalize_company(company)
        if not normalized:
            return None
        if normalized in self.index:
            return self.index[normalized]
        company_words = set(normalized.split())
        for indexed, original in self.index.items():
            overlap = company_words & set(indexed.split())
            if len(overlap) >= 2 and (normalized in indexed or indexed in normalized):
                return original
        return None
