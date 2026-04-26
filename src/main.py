from dotenv import load_dotenv

from src.config import EXPORTS_DIR, load_profile
from src.dedupe import dedupe_jobs
from src.job_sources import fetch_jobs
from src.matcher import rank_jobs
from src.notifier import render_html_report, send_email
from src.tracker import filter_jobs_for_email, save_jobs


def run(send: bool = True) -> None:
    load_dotenv()
    profile = load_profile()

    raw_jobs = fetch_jobs(profile)
    unique_jobs = dedupe_jobs(raw_jobs)
    ranked_jobs = rank_jobs(unique_jobs, profile)
    new_jobs = filter_jobs_for_email(ranked_jobs)

    max_email_jobs = int(profile["search"].get("max_email_jobs", 25))
    selected = new_jobs[:max_email_jobs]

    EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
    html = render_html_report(selected, profile)
    report_path = EXPORTS_DIR / "latest_report.html"
    report_path.write_text(html, encoding="utf-8")

    save_jobs(selected, emailed=send)

    if send and selected:
        send_email(
            subject=f"{len(selected)} new software/devops jobs matched your profile",
            html_body=html,
            recipient=profile["profile"]["email_recipient"],
        )

    print(
        f"Fetched: {len(raw_jobs)} | Unique: {len(unique_jobs)} | "
        f"Ranked: {len(ranked_jobs)} | New selected: {len(selected)}"
    )
    print(f"Report saved to: {report_path}")


if __name__ == "__main__":
    run(send=True)