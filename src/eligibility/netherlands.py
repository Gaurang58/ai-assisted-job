from __future__ import annotations

import csv
import io
import re

import openpyxl
import requests

from src.config import AppConfig
from src.eligibility.base import EligibilityResult
from src.eligibility.utils import Registry, detect_vacancy_signal
from src.models import Job
from src.normalization import strip_html


def download_nl_register(config: AppConfig) -> set[str]:
    url = config.data.get("eligibility", {}).get("nl_register_url", "")
    if not url:
        raise ValueError("Dutch recognised sponsor register URL is not configured")
    response = requests.get(url, timeout=45, headers={"User-Agent": "ai-assisted-job/1.0"})
    response.raise_for_status()
    if url.lower().endswith(".csv"):
        rows = csv.reader(io.StringIO(response.text))
        return {row[0].strip() for row in list(rows)[1:] if row and row[0].strip()}
    if url.lower().endswith((".xlsx", ".xlsm")):
        workbook = openpyxl.load_workbook(io.BytesIO(response.content), read_only=True)
        return {
            str(row[0]).strip()
            for row in workbook.active.iter_rows(min_row=2, values_only=True)
            if row and row[0]
        }
    companies = set()
    for table_row in re.findall(r"<tr\b[^>]*>(.*?)</tr>", response.text, re.I | re.S):
        cells = re.findall(r"<td\b[^>]*>(.*?)</td>", table_row, re.I | re.S)
        if cells:
            company = strip_html(cells[0])
            if company:
                companies.add(company)
    if not companies:
        raise ValueError("No employers were found on the Dutch recognised sponsor register page")
    return companies


class NetherlandsChecker:
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
            f"Employer matched the Dutch recognised sponsor register as {matched}"
            if matched
            else "Employer was not matched in the loaded Dutch register"
            if self.registry.index
            else "Dutch recognised sponsor register was unavailable"
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
            employer,
            evidence,
            signal,
            vacancy_evidence,
            "nl_highly_skilled_migrant" if matched or signal == "explicit_positive" else "",
            result,
            score,
        )
