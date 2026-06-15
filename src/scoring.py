from __future__ import annotations

import re

from src.config import AppConfig
from src.models import Job
from src.sponsorship import is_recruiter_company


def _contains(text: str, phrase: str) -> bool:
    return bool(re.search(rf"(?<!\w){re.escape(phrase.lower())}(?!\w)", text.lower()))


def score_job(job: Job, config: AppConfig) -> Job:
    title = job.title.lower()
    roles = config.data["roles"]["canonical"]
    excluded = config.data["roles"].get("excluded_titles", [])
    reasons: list[str] = []
    if any(_contains(title, term) for term in excluded):
        job.match_score = 0
        job.match_reasons = ["Excluded role title"]
        job.overall_score = round(job.eligibility_score * 0.3)
        return job

    canonical = None
    for role, settings in roles.items():
        if any(_contains(title, alias) for alias in settings.get("positive_titles", [])):
            canonical = role
            break
    if canonical is None:
        job.match_score = 0
        job.match_reasons = ["Not a configured target role"]
        job.overall_score = round(job.eligibility_score * 0.3)
        return job

    job.canonical_role = canonical
    score = 48
    reasons.append(f"Role: {canonical.replace('_', ' ')}")
    if any(_contains(title, term) for term in ("junior", "graduate", "entry level")):
        score += 10
        reasons.append("Early-career title")

    text = f"{job.title} {job.description}"
    high = [skill for skill in config.data["skills"].get("high_priority", []) if _contains(text, skill)]
    medium = [
        skill for skill in config.data["skills"].get("medium_priority", []) if _contains(text, skill)
    ]
    score += min(28, len(high) * 5) + min(12, len(medium) * 2)
    if high:
        reasons.append("Skills: " + ", ".join(high[:5]))
    else:
        score -= 8
        reasons.append("Few configured high-priority skills")

    salary = config.data["salary_preferences"].get(job.country_code or "")
    if job.annual_salary_min_local is None and job.annual_salary_max_local is None:
        score -= 5
        reasons.append("Salary not listed")
    elif salary and job.salary_currency == salary["currency"]:
        upper = job.annual_salary_max_local or job.annual_salary_min_local
        if upper is not None and upper < salary["preferred_min"]:
            score -= 10
            reasons.append("Salary below preferred minimum")
        else:
            score += 5
            reasons.append("Salary meets preference")

    if job.country_code in config.countries:
        score += 4
    if is_recruiter_company(job.company):
        score -= 6
        reasons.append("Recruiter or agency listing")
    elif len(job.description) >= 300:
        score += 5
        reasons.append("Direct/complete listing")

    job.match_score = max(0, min(100, round(score)))
    job.match_reasons = reasons
    job.overall_score = max(
        0, min(100, round(job.match_score * 0.70 + job.eligibility_score * 0.30))
    )
    return job


def rank_jobs(jobs: list[Job], config: AppConfig) -> list[Job]:
    scored = [score_job(job, config) for job in jobs]
    minimum_match = int(config.data["search"].get("minimum_match_score", 45))
    minimum_overall = int(config.data["search"].get("minimum_overall_score", 45))
    return sorted(
        [
            job
            for job in scored
            if job.match_score >= minimum_match and job.overall_score >= minimum_overall
        ],
        key=lambda job: (job.overall_score, job.match_score),
        reverse=True,
    )
