from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

import gspread
from google.oauth2.service_account import Credentials

from src.config import AppConfig
from src.models import Job
from src.storage.base import EmailBatch

LOGGER = logging.getLogger(__name__)
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

TRACKER_BOT_COLUMNS = [
    "Job ID", "Date Found", "Date Emailed", "Email Batch ID", "Country", "City",
    "Remote Type", "Job Title", "Company", "Source", "Job URL", "Salary Min",
    "Salary Max", "Currency", "Salary Period", "Match Score", "Work Authorisation",
    "Employer Evidence", "Vacancy Signal", "Permit Route", "Language",
]
TRACKER_USER_COLUMNS = [
    "Priority", "Application Status", "Applied Date", "Follow-up Date", "Next Action",
    "Contact Name", "Contact Email / LinkedIn", "CV Version", "Cover Letter",
    "Interview Date", "Outcome", "Notes",
]
STATE_COLUMNS = [
    "Job ID", "First Seen", "Last Seen", "Last Score", "Work Authorisation",
    "Email Status", "Email Batch ID", "Emailed At", "Last Error", "Source",
    "External ID", "Job URL",
]
EMAIL_COLUMNS = [
    "Batch ID", "Run Started", "Run Finished", "Status", "Jobs Selected",
    "Email Recipient", "Error",
]


def tracker_row(job: Job, batch: EmailBatch, now: str | None = None) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc).isoformat()
    return {
        "Job ID": job.job_id, "Date Found": job.fetched_at.date().isoformat(),
        "Date Emailed": now, "Email Batch ID": batch.batch_id,
        "Country": job.country_name or "", "City": job.city or "",
        "Remote Type": job.remote_type, "Job Title": job.title, "Company": job.company,
        "Source": job.source, "Job URL": job.url, "Salary Min": job.salary_min or "",
        "Salary Max": job.salary_max or "", "Currency": job.salary_currency or "",
        "Salary Period": job.salary_period or "unknown", "Match Score": job.match_score,
        "Work Authorisation": job.work_authorisation_result,
        "Employer Evidence": job.employer_evidence,
        "Vacancy Signal": job.vacancy_authorisation_signal,
        "Permit Route": job.permit_route, "Language": job.language or "",
    }


def merge_tracker_row(existing: dict[str, Any], bot_values: dict[str, Any]) -> dict[str, Any]:
    merged = dict(existing)
    merged.update(bot_values)
    for column in TRACKER_USER_COLUMNS:
        if existing.get(column) not in (None, ""):
            merged[column] = existing[column]
    return merged


class GoogleSheetsStore:
    def __init__(self, config: AppConfig, spreadsheet=None) -> None:
        self.config = config
        self._spreadsheet = spreadsheet

    @classmethod
    def from_environment(cls, config: AppConfig):
        sheet_id = os.getenv("GOOGLE_SHEET_ID")
        raw_credentials = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
        if not sheet_id or not raw_credentials:
            raise ValueError("GOOGLE_SHEET_ID and GOOGLE_SERVICE_ACCOUNT_JSON are required")
        try:
            info = json.loads(raw_credentials)
        except json.JSONDecodeError as exc:
            raise ValueError("GOOGLE_SERVICE_ACCOUNT_JSON is not valid JSON") from exc
        credentials = Credentials.from_service_account_info(info, scopes=SCOPES)
        spreadsheet = gspread.authorize(credentials).open_by_key(sheet_id)
        return cls(config, spreadsheet)

    def _worksheet(self, setting: str, headers: list[str]):
        title = self.config.data["google_sheets"][setting]
        try:
            worksheet = self._spreadsheet.worksheet(title)
        except gspread.WorksheetNotFound:
            worksheet = self._spreadsheet.add_worksheet(title=title, rows=1000, cols=len(headers))
        values = worksheet.get_all_values()
        if not values:
            worksheet.append_row(headers, value_input_option="RAW")
        return worksheet

    @staticmethod
    def _records(worksheet) -> tuple[list[str], list[dict[str, Any]]]:
        values = worksheet.get_all_values()
        if not values:
            return [], []
        headers = values[0]
        return headers, [dict(zip(headers, row + [""] * (len(headers) - len(row)))) for row in values[1:]]

    @staticmethod
    def _replace_rows(worksheet, headers: list[str], records: list[dict[str, Any]]) -> None:
        rows = [headers] + [[record.get(column, "") for column in headers] for record in records]
        worksheet.update(rows, "A1", value_input_option="USER_ENTERED")

    def get_seen_jobs(self) -> dict[str, dict]:
        worksheet = self._worksheet("state_worksheet", STATE_COLUMNS)
        _, records = self._records(worksheet)
        return {
            row["Job ID"]: {
                "score": int(row.get("Last Score") or 0),
                "emailed_at": row.get("Emailed At") or None,
                "email_batch_id": row.get("Email Batch ID") or None,
                "status": row.get("Email Status") or "seen",
            }
            for row in records if row.get("Job ID")
        }

    def upsert_seen_jobs(self, jobs: list[Job]) -> None:
        worksheet = self._worksheet("state_worksheet", STATE_COLUMNS)
        headers, records = self._records(worksheet)
        headers = headers or STATE_COLUMNS
        index = {row.get("Job ID"): row for row in records}
        now = datetime.now(timezone.utc).isoformat()
        for job in jobs:
            existing = index.get(job.job_id, {})
            values = {
                "Job ID": job.job_id, "First Seen": existing.get("First Seen") or now,
                "Last Seen": now, "Last Score": job.overall_score,
                "Work Authorisation": job.work_authorisation_result,
                "Email Status": existing.get("Email Status") or "seen",
                "Email Batch ID": existing.get("Email Batch ID") or "",
                "Emailed At": existing.get("Emailed At") or "",
                "Last Error": "", "Source": job.source,
                "External ID": job.external_id or "", "Job URL": job.url,
            }
            if existing:
                existing.update(values)
            else:
                records.append(values)
                index[job.job_id] = values
        self._replace_rows(worksheet, headers, records)
        LOGGER.info("google_sheets state_upserts=%d", len(jobs))

    def get_email_history(self) -> dict[str, dict]:
        worksheet = self._worksheet("email_log_worksheet", EMAIL_COLUMNS)
        _, records = self._records(worksheet)
        return {row["Batch ID"]: row for row in records if row.get("Batch ID")}

    def _upsert_email_log(self, batch: EmailBatch, status: str, error: str = "") -> None:
        worksheet = self._worksheet("email_log_worksheet", EMAIL_COLUMNS)
        headers, records = self._records(worksheet)
        headers = headers or EMAIL_COLUMNS
        row = next((item for item in records if item.get("Batch ID") == batch.batch_id), None)
        values = {
            "Batch ID": batch.batch_id, "Run Started": batch.run_started.isoformat(),
            "Run Finished": datetime.now(timezone.utc).isoformat() if status != "pending" else "",
            "Status": status, "Jobs Selected": len(batch.jobs),
            "Email Recipient": batch.recipient, "Error": error[:500],
        }
        if row:
            row.update(values)
        else:
            records.append(values)
        self._replace_rows(worksheet, headers, records)

    def mark_batch_pending(self, batch: EmailBatch) -> None:
        self._upsert_email_log(batch, "pending")

    def mark_batch_sent(self, batch: EmailBatch) -> None:
        state = self._worksheet("state_worksheet", STATE_COLUMNS)
        headers, records = self._records(state)
        now = datetime.now(timezone.utc).isoformat()
        selected = {job.job_id for job in batch.jobs}
        for row in records:
            if row.get("Job ID") in selected:
                row.update({
                    "Email Status": "sent", "Email Batch ID": batch.batch_id,
                    "Emailed At": now, "Last Error": "",
                })
        self._replace_rows(state, headers or STATE_COLUMNS, records)

        tracker = self._worksheet("tracker_worksheet", TRACKER_BOT_COLUMNS + TRACKER_USER_COLUMNS)
        tracker_headers, tracker_records = self._records(tracker)
        tracker_headers = tracker_headers or TRACKER_BOT_COLUMNS + TRACKER_USER_COLUMNS
        if tracker_headers[: len(TRACKER_BOT_COLUMNS)] != TRACKER_BOT_COLUMNS:
            raise ValueError("Jobs Tracker bot-managed columns do not match the required template")
        tracker_index = {
            row.get("Job ID"): (row_number, row)
            for row_number, row in enumerate(tracker_records, start=2)
        }
        updates = []
        appends = []
        for job in batch.jobs:
            bot_values = tracker_row(job, batch, now)
            existing = tracker_index.get(job.job_id)
            if existing:
                row_number, existing_values = existing
                existing_values.update(bot_values)
                updates.append({
                    "range": f"A{row_number}:U{row_number}",
                    "values": [[bot_values.get(column, "") for column in TRACKER_BOT_COLUMNS]],
                })
            else:
                new_row = merge_tracker_row({}, bot_values)
                appends.append([new_row.get(column, "") for column in tracker_headers])
        if updates:
            tracker.batch_update(updates, value_input_option="USER_ENTERED")
        if appends:
            tracker.append_rows(appends, value_input_option="USER_ENTERED")
        self._upsert_email_log(batch, "sent")
        LOGGER.info("google_sheets tracker_upserts=%d", len(batch.jobs))

    def mark_batch_failed(self, batch: EmailBatch, error: str) -> None:
        self._upsert_email_log(batch, "failed", error)

    def mark_batch_dry_run(self, batch: EmailBatch) -> None:
        self._upsert_email_log(batch, "dry_run")
