from __future__ import annotations

import hashlib
import logging
import sys
import time
import uuid
from datetime import datetime, timezone

from dotenv import load_dotenv

from src.cli import parse_args
from src.config import ConfigError, EXPORTS_DIR, load_config
from src.dedupe import cross_source_dedupe, exact_dedupe
from src.eligibility import EligibilityEngine
from src.job_sources import count_by_country, count_by_provider, fetch_jobs
from src.notifier import render_html_report, send_email
from src.scoring import rank_jobs
from src.storage import CompositeStore, EmailBatch, GoogleSheetsStore, SQLiteStore

LOGGER = logging.getLogger(__name__)
EMAIL_COUNTRY_ORDER = ("ie", "nl", "de", "gb", "unknown")


def make_batch_id(jobs, recipient: str, run_date: str | None = None) -> str:
    run_date = run_date or datetime.now(timezone.utc).date().isoformat()
    value = "|".join(sorted(job.job_id or "" for job in jobs)) + "|" + recipient + "|" + run_date
    return "jobs-" + hashlib.sha256(value.encode()).hexdigest()[:16]


def select_balanced_jobs(jobs, search_config: dict) -> list:
    maximum = int(search_config.get("max_email_jobs", 20))
    limits = search_config.get("email_country_limits", {})
    buckets = {
        code: [
            job
            for job in jobs
            if (job.country_code if job.country_code in {"gb", "de", "nl", "ie"} else "unknown")
            == code
        ]
        for code in EMAIL_COUNTRY_ORDER
    }
    selected = []
    positions = {code: 0 for code in EMAIL_COUNTRY_ORDER}
    while len(selected) < maximum:
        added = False
        for code in EMAIL_COUNTRY_ORDER:
            if len(selected) >= maximum:
                break
            country_limit = int(limits.get(code, maximum))
            already_selected = sum(
                1
                for job in selected
                if (job.country_code if job.country_code in {"gb", "de", "nl", "ie"} else "unknown")
                == code
            )
            if already_selected >= country_limit or positions[code] >= len(buckets[code]):
                continue
            selected.append(buckets[code][positions[code]])
            positions[code] += 1
            added = True
        if not added:
            break
    return selected


def _build_store(config, *, dry_run: bool, no_sheets: bool, sqlite_path=None):
    local = SQLiteStore(sqlite_path) if sqlite_path else SQLiteStore()
    if dry_run or no_sheets or not config.data["google_sheets"].get("enabled", True):
        return local
    sheets = GoogleSheetsStore.from_environment(config)
    return CompositeStore([local, sheets])


def run(
    *,
    dry_run: bool = False,
    no_email: bool = False,
    no_sheets: bool = False,
    providers=None,
    store=None,
    email_sender=send_email,
) -> dict:
    started = datetime.now(timezone.utc)
    started_clock = time.monotonic()
    run_id = uuid.uuid4().hex[:12]
    LOGGER.info("run_id=%s started", run_id)
    config = load_config()
    recipient = config.recipient or ""
    if not dry_run and not no_email and not recipient:
        raise ConfigError("EMAIL_RECIPIENT is required unless --dry-run or --no-email is used")
    store = store or _build_store(config, dry_run=dry_run, no_sheets=no_sheets)

    raw = fetch_jobs(config, providers=providers)
    exact = exact_dedupe(raw)
    max_age_days = int(config.data["search"].get("max_job_age_days", 14))
    age_cutoff = started.timestamp() - max_age_days * 86400
    current = [
        job
        for job in exact
        if job.created_at is None
        or (
            job.created_at.replace(tzinfo=timezone.utc)
            if job.created_at.tzinfo is None else job.created_at
        ).timestamp() >= age_cutoff
    ]
    engine = (
        EligibilityEngine(
            config,
            countries_needed={job.country_code for job in current if job.country_code},
        )
        if current else None
    )
    enriched = [engine.enrich(job) for job in current] if engine else []
    ranked = rank_jobs(enriched, config)
    ranked = sorted(cross_source_dedupe(ranked), key=lambda job: job.overall_score, reverse=True)

    existing = store.get_seen_jobs()
    if not dry_run:
        store.upsert_seen_jobs(ranked)
    new_jobs = [
        job for job in ranked
        if job.job_id not in existing
        or not existing[job.job_id].get("emailed_at")
        or job.overall_score >= int(existing[job.job_id].get("score") or 0) + 15
    ]
    selected = select_balanced_jobs(new_jobs, config.data["search"])
    batch = EmailBatch(
        make_batch_id(selected, recipient, started.date().isoformat()), started, selected, recipient
    )
    html = render_html_report(selected, config.data, batch.batch_id)
    EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report_path = EXPORTS_DIR / "latest_report.html"
    report_path.write_text(html, encoding="utf-8")

    if dry_run:
        LOGGER.info("run_id=%s batch=%s status=dry_run external_writes=0", run_id, batch.batch_id)
    elif no_email or not selected:
        store.mark_batch_dry_run(batch)
        LOGGER.info("run_id=%s batch=%s status=dry_run jobs=%d", run_id, batch.batch_id, len(selected))
    else:
        store.mark_batch_pending(batch)
        try:
            email_sender(
                f"{len(selected)} new software/devops jobs matched your profile",
                html,
                recipient,
            )
        except Exception as exc:
            safe_error = f"{type(exc).__name__}: {str(exc)[:300]}"
            store.mark_batch_failed(batch, safe_error)
            LOGGER.error("run_id=%s batch=%s status=failed error=%s", run_id, batch.batch_id, safe_error)
            raise
        store.mark_batch_sent(batch)
        LOGGER.info("run_id=%s batch=%s status=sent jobs=%d", run_id, batch.batch_id, len(selected))

    summary = {
        "run_id": run_id, "fetched": len(raw), "exact_unique": len(exact),
        "within_age": len(current),
        "ranked": len(ranked), "selected": len(selected),
        "providers": count_by_provider(raw), "countries": count_by_country(raw),
        "selected_countries": count_by_country(selected),
        "report": str(report_path), "elapsed_seconds": round(time.monotonic() - started_clock, 2),
    }
    LOGGER.info("run_summary=%s", summary)
    print(
        f"Fetched: {len(raw)} | Exact unique: {len(exact)} | "
        f"Ranked: {len(ranked)} | Email selected: {len(selected)}"
    )
    print(f"By provider: {summary['providers']}")
    print(f"By country: {summary['countries']}")
    print(f"Email selected by country: {summary['selected_countries']}")
    print(f"Report saved to: {report_path}")
    return summary


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    args = parse_args(argv)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    try:
        run(dry_run=args.dry_run, no_email=args.no_email, no_sheets=args.no_sheets)
    except (ConfigError, ValueError) as exc:
        LOGGER.error("configuration error: %s", exc)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
