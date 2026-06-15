from __future__ import annotations

from src.main import make_batch_id, run
from src.notifier import render_html_report, send_email


class OneJobProvider:
    name = "mock"

    def __init__(self, job):
        self.job = job

    def fetch(self, config):
        return [self.job]


class RecordingStore:
    def __init__(self):
        self.calls = []
        self.seen = {}

    def get_seen_jobs(self):
        return self.seen

    def upsert_seen_jobs(self, jobs):
        self.calls.append(("upsert", [job.job_id for job in jobs]))
        for job in jobs:
            self.seen[job.job_id] = {"score": job.overall_score, "emailed_at": None}

    def mark_batch_pending(self, batch):
        self.calls.append(("pending", batch.batch_id))

    def mark_batch_sent(self, batch):
        self.calls.append(("sent", batch.batch_id))

    def mark_batch_failed(self, batch, error):
        self.calls.append(("failed", batch.batch_id))

    def mark_batch_dry_run(self, batch):
        self.calls.append(("dry_run", batch.batch_id))


def test_batch_id_is_deterministic(job_factory):
    jobs = [job_factory(job_id="b"), job_factory(job_id="a", external_id="2")]
    assert make_batch_id(jobs, "x@example.com") == make_batch_id(list(reversed(jobs)), "x@example.com")


def test_email_failure_does_not_mark_jobs_sent(job_factory, monkeypatch):
    monkeypatch.setenv("EMAIL_RECIPIENT", "user@example.com")
    store = RecordingStore()

    def fail(*args):
        raise RuntimeError("SMTP unavailable")

    try:
        run(
            providers=[OneJobProvider(job_factory())], store=store,
            email_sender=fail, no_sheets=True,
        )
    except RuntimeError:
        pass
    assert [call[0] for call in store.calls] == ["upsert", "pending", "failed"]


def test_success_marks_sent_after_email(job_factory, monkeypatch):
    monkeypatch.setenv("EMAIL_RECIPIENT", "user@example.com")
    store = RecordingStore()
    sent = []
    run(
        providers=[OneJobProvider(job_factory())], store=store,
        email_sender=lambda *args: sent.append(True), no_sheets=True,
    )
    assert sent == [True]
    assert [call[0] for call in store.calls] == ["upsert", "pending", "sent"]


class FakeSMTP:
    messages = []

    def __init__(self, *args, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def starttls(self):
        pass

    def login(self, user, password):
        assert user == "sender@example.com"

    def send_message(self, message):
        self.messages.append(message)


def test_smtp_is_mockable(monkeypatch):
    monkeypatch.setenv("EMAIL_USER", "sender@example.com")
    monkeypatch.setenv("EMAIL_PASS", "secret")
    monkeypatch.setattr("src.notifier.smtplib.SMTP", FakeSMTP)
    send_email("Subject", "<p>Hello</p>", "recipient@example.com")
    assert FakeSMTP.messages[-1]["To"] == "recipient@example.com"


def test_dry_run_has_no_store_writes(job_factory):
    store = RecordingStore()
    run(providers=[OneJobProvider(job_factory())], store=store, dry_run=True)
    assert store.calls == []


def test_email_groups_each_country_once(job_factory):
    jobs = [
        job_factory(country_code="de", country_name="Germany", external_id="de-1"),
        job_factory(country_code="gb", country_name="United Kingdom", external_id="gb-1"),
        job_factory(country_code="de", country_name="Germany", external_id="de-2"),
        job_factory(country_code="nl", country_name="Netherlands", external_id="nl-1"),
    ]
    html = render_html_report(jobs, {"profile": {"name": "Gaurang"}}, "batch-1")
    assert html.count(">Germany</td>") == 1
    assert html.count(">United Kingdom</td>") == 1
    assert html.count(">Netherlands</td>") == 1
    assert html.index(">United Kingdom</td>") < html.index(">Germany</td>")
    assert html.index(">Germany</td>") < html.index(">Netherlands</td>")


def test_email_uses_aligned_email_safe_layout(job_factory):
    html = render_html_report(
        [job_factory(work_authorisation_result="possible", match_score=88)],
        {"profile": {"name": "Gaurang"}},
        "batch-1",
    )
    assert 'width="680"' in html
    assert 'role="presentation"' in html
    assert "View job and apply" in html
    assert "Match score" in html
    assert "88/100" in html
