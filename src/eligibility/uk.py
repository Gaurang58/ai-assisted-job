from __future__ import annotations

import io
import re

import openpyxl
import requests

from src.config import AppConfig
from src.eligibility.base import EligibilityResult
from src.eligibility.utils import Registry, detect_vacancy_signal
from src.models import Job


def download_uk_register(config: AppConfig) -> set[str]:
    page_url = config.data["eligibility"]["uk_register_url"]
    page = requests.get(page_url, timeout=20, headers={"User-Agent": "ai-assisted-job/1.0"})
    page.raise_for_status()
    matches = re.findall(
        r'href="(https://assets\.publishing\.service\.gov\.uk[^"]+\.(?:xlsx|csv))"',
        page.text,
        re.IGNORECASE,
    )
    if not matches:
        raise ValueError("UK sponsor register download link was not found")
    response = requests.get(matches[0], timeout=45, headers={"User-Agent": "ai-assisted-job/1.0"})
    response.raise_for_status()
    if matches[0].lower().endswith(".csv"):
        return {
            line.split(",")[0].strip().strip('"')
            for line in response.text.splitlines()[1:]
            if line.strip()
        }
    workbook = openpyxl.load_workbook(io.BytesIO(response.content), read_only=True)
    return {
        str(row[0]).strip()
        for row in workbook.active.iter_rows(min_row=2, values_only=True)
        if row and row[0]
    }


class UkChecker:
    def __init__(self, registry: Registry, positive_terms: list[str], negative_terms: list[str]):
        self.registry = registry
        self.positive_terms = positive_terms
        self.negative_terms = negative_terms

    def check(self, job: Job) -> EligibilityResult:
        signal, vacancy_evidence = detect_vacancy_signal(
            job, self.positive_terms, self.negative_terms
        )
        matched = self.registry.match(job.company)
        employer = "recognised_or_licensed" if matched else (
            "not_found" if self.registry.index else "unknown"
        )
        evidence = (
            f"Employer matched the UK licensed sponsor register as {matched}"
            if matched
            else "Employer was not matched in the loaded UK register"
            if self.registry.index
            else "UK sponsor register was unavailable"
        )
        if signal == "explicit_negative":
            result, score = "unlikely", 0
        elif matched and signal == "explicit_positive":
            result, score = "strong", 95
        elif matched or signal == "explicit_positive":
            result, score = "possible", 65
        else:
            result, score = "unknown", 30
        return EligibilityResult(
            employer, evidence, signal, vacancy_evidence, "uk_skilled_worker", result, score
        )
