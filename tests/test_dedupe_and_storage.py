from datetime import datetime, timezone

from src.dedupe import cross_source_dedupe, exact_dedupe
from src.storage.base import EmailBatch
from src.storage.google_sheets_store import merge_tracker_row, tracker_row
from src.storage.sqlite_store import SQLiteStore


def test_exact_deduplication(job_factory):
    jobs = [job_factory(), job_factory(title="Changed title")]
    assert len(exact_dedupe(jobs)) == 1


def test_cross_source_dedupe_does_not_require_salary(job_factory):
    first = job_factory(source="adzuna", external_id="a", salary_min=40000, overall_score=80)
    second = job_factory(
        source="rss", external_id="b", salary_min=90000, overall_score=70,
        url="https://direct.example.test/jobs/1",
    )
    exact_dedupe([first, second])
    result = cross_source_dedupe([first, second])
    assert len(result) == 1
    assert result[0].source == "rss"
    assert result[0].alternate_urls


def test_google_sheets_row_mapping(job_factory):
    job = job_factory(job_id="job-1", match_score=77, work_authorisation_result="possible")
    batch = EmailBatch("batch-1", datetime.now(timezone.utc), [job], "user@example.com")
    row = tracker_row(job, batch, "2026-06-14T12:00:00+00:00")
    assert row["Job ID"] == "job-1"
    assert row["Country"] == "Germany"
    assert row["Currency"] == "EUR"
    assert row["Email Batch ID"] == "batch-1"


def test_user_editable_tracker_columns_are_preserved():
    existing = {"Job ID": "1", "Application Status": "Applied", "Notes": "Follow up"}
    merged = merge_tracker_row(existing, {"Job ID": "1", "Company": "Updated"})
    assert merged["Application Status"] == "Applied"
    assert merged["Notes"] == "Follow up"
    assert merged["Company"] == "Updated"


def test_sqlite_batch_idempotency(tmp_path, job_factory):
    store = SQLiteStore(tmp_path / "jobs.db")
    job = job_factory(job_id="job-1", overall_score=75)
    store.upsert_seen_jobs([job])
    batch = EmailBatch("batch-1", datetime.now(timezone.utc), [job], "user@example.com")
    store.mark_batch_pending(batch)
    store.mark_batch_pending(batch)
    assert len(store.get_email_history()) == 1
    store.mark_batch_sent(batch)
    assert store.get_seen_jobs()["job-1"]["email_batch_id"] == "batch-1"


class FakeWorksheet:
    def __init__(self, values=None):
        self.values = values or []

    def get_all_values(self):
        return self.values

    def append_row(self, row, **kwargs):
        self.values.append(list(row))

    def update(self, rows, range_name, **kwargs):
        self.values = [list(row) for row in rows]

    def append_rows(self, rows, **kwargs):
        self.values.extend([list(row) for row in rows])

    def batch_update(self, updates, **kwargs):
        for update in updates:
            row_number = int(update["range"].split(":")[0][1:])
            while len(self.values) < row_number:
                self.values.append([])
            row = self.values[row_number - 1]
            values = update["values"][0]
            self.values[row_number - 1] = values + row[len(values):]


class FakeSpreadsheet:
    def __init__(self):
        self.sheets = {}

    def worksheet(self, title):
        import gspread
        if title not in self.sheets:
            raise gspread.WorksheetNotFound(title)
        return self.sheets[title]

    def add_worksheet(self, title, rows, cols):
        self.sheets[title] = FakeWorksheet()
        return self.sheets[title]


def test_google_sheets_mocked_batch_upsert(config, job_factory):
    from src.storage.google_sheets_store import GoogleSheetsStore, TRACKER_BOT_COLUMNS, TRACKER_USER_COLUMNS

    spreadsheet = FakeSpreadsheet()
    store = GoogleSheetsStore(config, spreadsheet)
    job = job_factory(job_id="job-1", overall_score=80)
    store.upsert_seen_jobs([job])
    batch = EmailBatch("batch-1", datetime.now(timezone.utc), [job], "user@example.com")
    store.mark_batch_pending(batch)
    store.mark_batch_sent(batch)
    tracker = spreadsheet.sheets["Jobs Tracker"].values
    headers = tracker[0]
    row = dict(zip(headers, tracker[1]))
    assert row["Job ID"] == "job-1"
    assert row["Email Batch ID"] == "batch-1"
    assert headers == TRACKER_BOT_COLUMNS + TRACKER_USER_COLUMNS
