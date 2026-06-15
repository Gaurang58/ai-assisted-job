from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from src.models import Job


@dataclass(frozen=True)
class EmailBatch:
    batch_id: str
    run_started: datetime
    jobs: list[Job]
    recipient: str


class Storage(Protocol):
    def get_seen_jobs(self) -> dict[str, dict]: ...
    def upsert_seen_jobs(self, jobs: list[Job]) -> None: ...
    def get_email_history(self) -> dict[str, dict]: ...
    def mark_batch_pending(self, batch: EmailBatch) -> None: ...
    def mark_batch_sent(self, batch: EmailBatch) -> None: ...
    def mark_batch_failed(self, batch: EmailBatch, error: str) -> None: ...
    def mark_batch_dry_run(self, batch: EmailBatch) -> None: ...
