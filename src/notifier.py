from __future__ import annotations

import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from html import escape

from src.models import Job


def format_salary(job: Job) -> str:
    if job.salary_min is None and job.salary_max is None:
        return "Not listed"
    values = [value for value in (job.salary_min, job.salary_max) if value is not None]
    amount = f"{values[0]:,.0f}" if len(values) == 1 else f"{values[0]:,.0f}–{values[-1]:,.0f}"
    return f"{job.salary_currency or ''} {amount} ({job.salary_period or 'unknown'})".strip()


def render_html_report(jobs: list[Job], profile: dict, batch_id: str) -> str:
    cards = []
    current_country = None
    colours = {
        "strong": "#166534", "possible": "#1d4ed8",
        "unknown": "#6b7280", "unlikely": "#b91c1c",
    }
    for job in jobs:
        country = job.country_name or "Unknown / global"
        if country != current_country:
            cards.append(f"<h2 style='margin-top:28px'>{escape(country)}</h2>")
            current_country = country
        result = job.work_authorisation_result
        created = job.created_at.date().isoformat() if job.created_at else "Not listed"
        reasons = ", ".join(job.match_reasons) or "Profile match"
        cards.append(
            f"""
            <section style="border:1px solid #ddd;border-radius:10px;padding:16px;margin:12px 0">
              <h3 style="margin:0 0 6px"><a href="{escape(job.url, quote=True)}">{escape(job.title)}</a></h3>
              <p><strong>{escape(job.company)}</strong> · {escape(country)}
              {(" · " + escape(job.city)) if job.city else ""} · {escape(job.remote_type)}</p>
              <p><strong>Source:</strong> {escape(job.source)} ·
              <strong>Posted:</strong> {created} · <strong>Salary:</strong> {escape(format_salary(job))}</p>
              <p><strong>Match score:</strong> {job.match_score}/100 ·
              <strong style="color:{colours.get(result, '#6b7280')}">Work authorisation: {escape(result)}</strong></p>
              <p><strong>Employer evidence:</strong> {escape(job.employer_evidence or "None")}</p>
              <p><strong>Vacancy evidence:</strong> {escape(job.vacancy_evidence or "None")} ·
              <strong>Permit route:</strong> {escape(job.permit_route or "Not identified")}</p>
              <p><strong>Why matched:</strong> {escape(reasons)}</p>
              <p><a href="{escape(job.url, quote=True)}">Apply / view original listing</a></p>
            </section>
            """
        )
    return f"""
    <!doctype html><html><head><meta name="viewport" content="width=device-width"></head>
    <body style="font-family:Arial,sans-serif;max-width:820px;margin:auto;padding:16px;line-height:1.45">
      <h1>AI-assisted Job Search Results</h1>
      <p>{len(jobs)} ranked jobs for {escape(profile["profile"]["name"])}.</p>
      <p><strong>Batch ID:</strong> {escape(batch_id)}</p>
      <p style="background:#fff7ed;padding:10px;border-radius:6px">
        Work-authorisation results are evidence-based guidance, not legal advice or a guaranteed visa outcome.
      </p>
      {''.join(cards) if cards else '<p>No new matching jobs were selected.</p>'}
    </body></html>
    """


def send_email(subject: str, html_body: str, recipient: str) -> None:
    email_user = os.getenv("EMAIL_USER")
    email_pass = os.getenv("EMAIL_PASS")
    smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    if not email_user or not email_pass:
        raise RuntimeError("EMAIL_USER and EMAIL_PASS are required to send email")
    message = MIMEMultipart("alternative")
    message["Subject"] = subject
    message["From"] = email_user
    message["To"] = recipient
    message.attach(MIMEText(html_body, "html", "utf-8"))
    with smtplib.SMTP(smtp_host, smtp_port, timeout=30) as server:
        server.starttls()
        server.login(email_user, email_pass)
        server.send_message(message)
