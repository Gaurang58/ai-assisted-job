from __future__ import annotations

import logging

from src.models import Job
from src.storage.base import EmailBatch

LOGGER = logging.getLogger(__name__)


class CompositeStore:
    def __init__(self, stores: list) -> None:
        self.stores = stores

    def get_seen_jobs(self) -> dict[str, dict]:
        merged: dict[str, dict] = {}
        for store in self.stores:
            merged.update(store.get_seen_jobs())
        return merged

    def get_email_history(self) -> dict[str, dict]:
        merged: dict[str, dict] = {}
        for store in self.stores:
            merged.update(store.get_email_history())
        return merged

    def _call(self, method: str, *args) -> None:
        errors = []
        for store in self.stores:
            try:
                getattr(store, method)(*args)
            except Exception as exc:
                LOGGER.exception("storage=%s operation=%s failed=%s", type(store).__name__, method, exc)
                errors.append(exc)
        if errors:
            raise RuntimeError(f"{method} failed for {len(errors)} storage backend(s)")

    def upsert_seen_jobs(self, jobs: list[Job]) -> None:
        self._call("upsert_seen_jobs", jobs)

    def mark_batch_pending(self, batch: EmailBatch) -> None:
        self._call("mark_batch_pending", batch)

    def mark_batch_sent(self, batch: EmailBatch) -> None:
        self._call("mark_batch_sent", batch)

    def mark_batch_failed(self, batch: EmailBatch, error: str) -> None:
        self._call("mark_batch_failed", batch, error)

    def mark_batch_dry_run(self, batch: EmailBatch) -> None:
        self._call("mark_batch_dry_run", batch)
