"""Selection helpers and compatibility access to local SQLite state."""

from __future__ import annotations

from src.models import Job
from src.storage.sqlite_store import SQLiteStore


def filter_jobs_for_email(jobs: list[Job], store=None) -> list[Job]:
    store = store or SQLiteStore()
    existing = store.get_seen_jobs()
    selected = []
    for job in jobs:
        previous = existing.get(job.job_id or "")
        if previous is None or not previous.get("emailed_at"):
            selected.append(job)
        elif job.overall_score >= int(previous.get("score") or 0) + 15:
            selected.append(job)
    return selected


def save_jobs(jobs: list[Job], emailed: bool = False) -> None:
    store = SQLiteStore()
    store.upsert_seen_jobs(jobs)
