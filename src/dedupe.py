from __future__ import annotations

import hashlib
import re
from urllib.parse import urlsplit, urlunsplit

from src.models import Job
from src.sponsorship import is_recruiter_company


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", (value or "").lower())).strip()


def canonical_url(value: str) -> str:
    if not value:
        return ""
    parts = urlsplit(value)
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip("/"), "", ""))


def normalize_title(value: str) -> str:
    text = clean_text(value)
    for old, new in {
        "node js": "nodejs",
        "front end": "frontend",
        "full stack": "fullstack",
        "dev ops": "devops",
        "site reliability engineer": "sre",
        "software developer": "software engineer",
    }.items():
        text = text.replace(old, new)
    return text


def normalize_company(value: str) -> str:
    words = clean_text(value).split()
    suffixes = {"ltd", "limited", "plc", "llc", "inc", "gmbh", "bv"}
    return " ".join(word for word in words if word not in suffixes)


def make_job_id(job: Job) -> str:
    if job.external_id:
        raw = f"{job.source}|{job.external_id}"
    else:
        raw = "|".join(
            [
                normalize_title(job.title),
                normalize_company(job.company),
                job.country_code or "",
                clean_text(job.city or ""),
                canonical_url(job.url),
            ]
        )
    return hashlib.sha256(raw.encode()).hexdigest()[:20]


def exact_dedupe(jobs: list[Job]) -> list[Job]:
    seen: set[str] = set()
    unique: list[Job] = []
    for job in jobs:
        job.job_id = make_job_id(job)
        if job.job_id in seen:
            continue
        seen.add(job.job_id)
        unique.append(job)
    return unique


def soft_key(job: Job) -> str:
    place = clean_text(job.city or job.remote_type)
    return "|".join(
        [normalize_title(job.title), normalize_company(job.company), job.country_code or "", place]
    )


def _quality(job: Job) -> tuple:
    direct = int(job.source not in {"adzuna", "reed"} and not is_recruiter_company(job.company))
    explicit = int(job.vacancy_authorisation_signal == "explicit_positive")
    created = job.created_at.timestamp() if job.created_at else 0
    return direct, len(job.description), int(bool(job.url)), explicit, created, job.overall_score


def cross_source_dedupe(jobs: list[Job]) -> list[Job]:
    chosen: dict[str, Job] = {}
    for job in jobs:
        key = soft_key(job)
        existing = chosen.get(key)
        if existing is None:
            chosen[key] = job
            continue
        winner, loser = (job, existing) if _quality(job) > _quality(existing) else (existing, job)
        urls = list(dict.fromkeys(winner.alternate_urls + loser.alternate_urls + [loser.url]))
        winner.alternate_urls = [url for url in urls if url and url != winner.url]
        chosen[key] = winner
    return list(chosen.values())


def dedupe_jobs(jobs: list[Job]) -> list[Job]:
    return exact_dedupe(jobs)
