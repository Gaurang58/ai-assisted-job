from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from src.config import DB_PATH
from src.models import Job
from src.storage.base import EmailBatch


class SQLiteStore:
    def __init__(self, db_path: Path = DB_PATH) -> None:
        self.db_path = db_path
        self._init_db()

    def connect(self):
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        return sqlite3.connect(self.db_path)

    def _columns(self, conn, table: str) -> set[str]:
        return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}

    def _init_db(self) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    job_id TEXT PRIMARY KEY, title TEXT, company TEXT, location TEXT,
                    url TEXT, source TEXT, score INTEGER, sponsorship_status TEXT,
                    salary_min REAL, salary_max REAL, currency TEXT, first_seen TEXT,
                    last_seen TEXT, emailed_at TEXT, status TEXT DEFAULT 'new'
                )
                """
            )
            migrations = {
                "country_code": "TEXT", "city": "TEXT", "remote_type": "TEXT",
                "match_score": "INTEGER", "overall_score": "INTEGER",
                "work_authorisation": "TEXT", "email_batch_id": "TEXT",
                "external_id": "TEXT", "last_error": "TEXT",
            }
            columns = self._columns(conn, "jobs")
            for name, sql_type in migrations.items():
                if name not in columns:
                    conn.execute(f"ALTER TABLE jobs ADD COLUMN {name} {sql_type}")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS email_batches (
                    batch_id TEXT PRIMARY KEY, run_started TEXT, run_finished TEXT,
                    status TEXT, jobs_selected INTEGER, recipient TEXT, error TEXT
                )
                """
            )

    def get_seen_jobs(self) -> dict[str, dict]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT job_id, overall_score, emailed_at, email_batch_id, status FROM jobs"
            ).fetchall()
        return {
            row[0]: {
                "score": row[1] or 0,
                "emailed_at": row[2],
                "email_batch_id": row[3],
                "status": row[4],
            }
            for row in rows
        }

    def upsert_seen_jobs(self, jobs: list[Job]) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self.connect() as conn:
            conn.executemany(
                """
                INSERT INTO jobs (
                    job_id, title, company, location, url, source, score,
                    sponsorship_status, salary_min, salary_max, currency,
                    first_seen, last_seen, status, country_code, city, remote_type,
                    match_score, overall_score, work_authorisation, external_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'seen', ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(job_id) DO UPDATE SET
                    last_seen=excluded.last_seen, title=excluded.title,
                    company=excluded.company, url=excluded.url,
                    match_score=excluded.match_score, overall_score=excluded.overall_score,
                    score=excluded.score, work_authorisation=excluded.work_authorisation,
                    sponsorship_status=excluded.sponsorship_status
                """,
                [
                    (
                        job.job_id, job.title, job.company, job.location_raw, job.url, job.source,
                        job.overall_score, job.work_authorisation_result, job.salary_min,
                        job.salary_max, job.salary_currency, now, now, job.country_code, job.city,
                        job.remote_type, job.match_score, job.overall_score,
                        job.work_authorisation_result, job.external_id,
                    )
                    for job in jobs
                ],
            )

    def get_email_history(self) -> dict[str, dict]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT batch_id, status, jobs_selected, error FROM email_batches"
            ).fetchall()
        return {row[0]: {"status": row[1], "jobs_selected": row[2], "error": row[3]} for row in rows}

    def _upsert_batch(self, batch: EmailBatch, status: str, error: str = "") -> None:
        finished = datetime.now(timezone.utc).isoformat() if status != "pending" else None
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO email_batches VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(batch_id) DO UPDATE SET
                    run_finished=excluded.run_finished, status=excluded.status,
                    jobs_selected=excluded.jobs_selected, recipient=excluded.recipient,
                    error=excluded.error
                """,
                (
                    batch.batch_id, batch.run_started.isoformat(), finished, status,
                    len(batch.jobs), batch.recipient, error[:500],
                ),
            )

    def mark_batch_pending(self, batch: EmailBatch) -> None:
        self._upsert_batch(batch, "pending")

    def mark_batch_sent(self, batch: EmailBatch) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self.connect() as conn:
            conn.executemany(
                """
                UPDATE jobs SET emailed_at=?, status='emailed', email_batch_id=?, last_error=NULL
                WHERE job_id=?
                """,
                [(now, batch.batch_id, job.job_id) for job in batch.jobs],
            )
        self._upsert_batch(batch, "sent")

    def mark_batch_failed(self, batch: EmailBatch, error: str) -> None:
        with self.connect() as conn:
            conn.executemany(
                "UPDATE jobs SET status='seen', last_error=? WHERE job_id=?",
                [(error[:500], job.job_id) for job in batch.jobs],
            )
        self._upsert_batch(batch, "failed", error)

    def mark_batch_dry_run(self, batch: EmailBatch) -> None:
        self._upsert_batch(batch, "dry_run")
