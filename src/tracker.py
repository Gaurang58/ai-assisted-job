import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List

from src.config import DB_PATH


def connect(db_path: Path = DB_PATH):
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(db_path)


def init_db() -> None:
    with connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS jobs (
                job_id TEXT PRIMARY KEY,
                title TEXT,
                company TEXT,
                location TEXT,
                url TEXT,
                source TEXT,
                score INTEGER,
                sponsorship_status TEXT,
                salary_min REAL,
                salary_max REAL,
                currency TEXT,
                first_seen TEXT,
                last_seen TEXT,
                emailed_at TEXT,
                status TEXT DEFAULT 'new'
            )
            """
        )
        conn.commit()


def get_existing_jobs() -> dict:
    init_db()
    with connect() as conn:
        rows = conn.execute(
            "SELECT job_id, score, emailed_at FROM jobs"
        ).fetchall()

    return {
        row[0]: {
            "score": row[1],
            "emailed_at": row[2],
        }
        for row in rows
    }


def save_jobs(jobs: Iterable[Dict], emailed: bool = False) -> None:
    init_db()
    now = datetime.now(timezone.utc).isoformat()

    with connect() as conn:
        for job in jobs:
            conn.execute(
                """
                INSERT INTO jobs (
                    job_id, title, company, location, url, source, score,
                    sponsorship_status, salary_min, salary_max, currency,
                    first_seen, last_seen, emailed_at, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(job_id) DO UPDATE SET
                    last_seen=excluded.last_seen,
                    score=excluded.score,
                    sponsorship_status=excluded.sponsorship_status,
                    emailed_at=CASE
                        WHEN excluded.score > jobs.score THEN NULL
                        ELSE jobs.emailed_at
                    END
                """,
                (
                    job.get("job_id"),
                    job.get("title"),
                    job.get("company"),
                    job.get("location"),
                    job.get("url"),
                    job.get("source"),
                    job.get("score"),
                    job.get("sponsorship_status"),
                    job.get("salary_min"),
                    job.get("salary_max"),
                    job.get("currency"),
                    now,
                    now,
                    now if emailed else None,
                    "emailed" if emailed else "new",
                ),
            )
        conn.commit()


def filter_jobs_for_email(jobs: List[Dict]) -> List[Dict]:
    existing = get_existing_jobs()
    selected = []

    for job in jobs:
        job_id = job.get("job_id")
        current_score = job.get("score", 0)

        if job_id not in existing:
            selected.append(job)
            continue

        previous = existing[job_id]

        # If never emailed → include
        if not previous["emailed_at"]:
            selected.append(job)
            continue

        # If score improved significantly → resurface
        if current_score >= previous["score"] + 15:
            selected.append(job)

    return selected