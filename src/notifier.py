from __future__ import annotations

import os
import smtplib
from collections import OrderedDict
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from html import escape

from src.models import Job

COUNTRY_ORDER = ("gb", "de", "nl", "ie")
COUNTRY_LABELS = {
    "gb": "United Kingdom",
    "de": "Germany",
    "nl": "Netherlands",
    "ie": "Ireland",
    "unknown": "Remote / country not identified",
}
AUTH_STYLES = {
    "strong": ("#166534", "#dcfce7"),
    "possible": ("#1d4ed8", "#dbeafe"),
    "unknown": ("#4b5563", "#f3f4f6"),
    "unlikely": ("#b91c1c", "#fee2e2"),
}


def format_salary(job: Job) -> str:
    if job.salary_min is None and job.salary_max is None:
        return "Not listed"
    values = [value for value in (job.salary_min, job.salary_max) if value is not None]
    amount = f"{values[0]:,.0f}" if len(values) == 1 else f"{values[0]:,.0f} - {values[-1]:,.0f}"
    return f"{job.salary_currency or ''} {amount}".strip()


def _remote_label(value: str) -> str:
    return {
        "onsite": "On-site",
        "hybrid": "Hybrid",
        "remote": "Remote",
        "remote_country_restricted": "Remote (restricted)",
        "unknown": "Not specified",
    }.get(value, value.replace("_", " ").title())


def _group_jobs(jobs: list[Job]) -> list[tuple[str, list[Job]]]:
    grouped: OrderedDict[str, list[Job]] = OrderedDict()
    for code in COUNTRY_ORDER:
        matching = [job for job in jobs if job.country_code == code]
        if matching:
            grouped[code] = matching
    unknown = [job for job in jobs if job.country_code not in COUNTRY_ORDER]
    if unknown:
        grouped["unknown"] = unknown
    return list(grouped.items())


def _short_evidence(job: Job) -> str:
    employer = job.employer_evidence or "No employer evidence"
    vacancy = job.vacancy_evidence or "Vacancy wording not found"
    route = job.permit_route or "Route not identified"
    return f"Employer: {employer} | Vacancy: {vacancy} | Route: {route}"


def _job_rows(job: Job, number: int) -> str:
    result = job.work_authorisation_result or "unknown"
    auth_text, auth_background = AUTH_STYLES.get(result, AUTH_STYLES["unknown"])
    country = job.country_name or COUNTRY_LABELS["unknown"]
    location = ", ".join(value for value in (job.city, country) if value)
    created = job.created_at.date().isoformat() if job.created_at else "Not listed"
    link = escape(job.url, quote=True)
    return f"""
      <tr>
        <td valign="top" align="center" style="padding:11px 7px;border-bottom:1px solid #e5e7eb;
                                               color:#64748b;font-size:12px">{number}</td>
        <td valign="top" style="padding:11px 9px;border-bottom:1px solid #e5e7eb">
          <a href="{link}" style="color:#153e75;font-size:14px;line-height:18px;
                                  font-weight:700;text-decoration:none">{escape(job.title)}</a>
          <div style="padding-top:2px;color:#475569;font-size:12px;line-height:16px">
            {escape(job.company)}
          </div>
        </td>
        <td valign="top" style="padding:11px 9px;border-bottom:1px solid #e5e7eb;
                                color:#334155;font-size:12px;line-height:17px">
          {escape(location)}<br>
          <span style="color:#64748b">{escape(_remote_label(job.remote_type))}</span>
        </td>
        <td valign="top" style="padding:11px 9px;border-bottom:1px solid #e5e7eb;
                                color:#334155;font-size:12px;line-height:17px">
          {escape(format_salary(job))}<br>
          <span style="color:#64748b">{escape(job.source.title())} · {escape(created)}</span>
        </td>
        <td valign="top" style="padding:11px 9px;border-bottom:1px solid #e5e7eb;
                                color:#334155;font-size:12px;line-height:17px">
          <strong>{job.match_score}/100</strong><br>
          <span style="display:inline-block;margin-top:3px;padding:2px 6px;border-radius:10px;
                       color:{auth_text};background:{auth_background};font-size:10px;
                       line-height:14px;font-weight:700;text-transform:uppercase">
            {escape(result)}
          </span>
        </td>
        <td valign="middle" align="center" style="padding:11px 8px;border-bottom:1px solid #e5e7eb">
          <a href="{link}" style="display:inline-block;padding:7px 9px;border-radius:5px;
                                  background:#1d4ed8;color:#ffffff;font-size:11px;
                                  line-height:14px;font-weight:700;text-decoration:none;
                                  white-space:nowrap">Open job</a>
        </td>
      </tr>
      <tr>
        <td></td>
        <td colspan="5" style="padding:5px 9px 10px;border-bottom:1px solid #dbe3ef;
                               color:#64748b;font-size:10px;line-height:14px">
          <strong style="color:#475569">Evidence:</strong> {escape(_short_evidence(job))}
        </td>
      </tr>
    """


def render_html_report(jobs: list[Job], profile: dict, batch_id: str) -> str:
    groups = _group_jobs(jobs)
    sections = []
    number = 1
    for code, country_jobs in groups:
        rows = []
        for job in country_jobs:
            rows.append(_job_rows(job, number))
            number += 1
        sections.append(
            f"""
            <tr>
              <td style="padding:18px 0 7px">
                <table role="presentation" width="100%" cellpadding="0" cellspacing="0"
                       style="border-collapse:collapse">
                  <tr>
                    <td data-country-section="{code}"
                        style="padding:9px 12px;background:#153e75;color:#ffffff;
                               font-size:15px;line-height:20px;font-weight:700">
                      {escape(COUNTRY_LABELS[code])}
                    </td>
                    <td align="right" style="padding:9px 12px;background:#153e75;color:#dbeafe;
                                            font-size:12px;line-height:20px">
                      {len(country_jobs)} {"job" if len(country_jobs) == 1 else "jobs"}
                    </td>
                  </tr>
                </table>
                <table role="presentation" width="100%" cellpadding="0" cellspacing="0"
                       style="width:100%;border:1px solid #dbe3ef;border-collapse:collapse;
                              table-layout:fixed;background:#ffffff">
                  <tr style="background:#f1f5f9">
                    <th width="4%" style="padding:7px;color:#475569;font-size:10px">#</th>
                    <th width="29%" align="left" style="padding:7px 9px;color:#475569;
                                                       font-size:10px">JOB / COMPANY</th>
                    <th width="20%" align="left" style="padding:7px 9px;color:#475569;
                                                       font-size:10px">LOCATION</th>
                    <th width="21%" align="left" style="padding:7px 9px;color:#475569;
                                                       font-size:10px">SALARY / SOURCE</th>
                    <th width="14%" align="left" style="padding:7px 9px;color:#475569;
                                                       font-size:10px">MATCH</th>
                    <th width="12%" style="padding:7px;color:#475569;font-size:10px">LINK</th>
                  </tr>
                  {''.join(rows)}
                </table>
              </td>
            </tr>
            """
        )

    body = "".join(sections) if sections else """
      <tr><td style="padding:28px;text-align:center;color:#64748b">
        No new matching jobs were selected.
      </td></tr>
    """
    return f"""
    <!doctype html>
    <html>
      <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width,initial-scale=1">
        <meta name="x-apple-disable-message-reformatting">
      </head>
      <body style="margin:0;padding:0;background:#f3f6fa;font-family:Arial,Helvetica,sans-serif">
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0"
               style="width:100%;background:#f3f6fa">
          <tr>
            <td align="center" style="padding:18px 8px">
              <table role="presentation" width="760" cellpadding="0" cellspacing="0"
                     style="width:100%;max-width:760px">
                <tr>
                  <td style="padding:18px 20px;background:#153e75;color:#ffffff">
                    <div style="font-size:22px;line-height:28px;font-weight:700">
                      Job matches by country
                    </div>
                    <div style="padding-top:4px;font-size:13px;line-height:19px;color:#dbeafe">
                      {len(jobs)} new roles for {escape(profile["profile"]["name"])}
                    </div>
                  </td>
                </tr>
                <tr>
                  <td style="padding:10px 14px;background:#fff7ed;color:#7c2d12;
                             font-size:11px;line-height:16px">
                    Work-authorisation labels are evidence-based guidance, not legal advice.
                    Every blue "Open job" button links to the original vacancy.
                  </td>
                </tr>
                <tr>
                  <td style="padding:0 12px 18px;background:#ffffff">
                    <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
                      {body}
                    </table>
                  </td>
                </tr>
                <tr>
                  <td align="center" style="padding:12px;background:#e8eef7;color:#64748b;
                                           font-size:10px;line-height:15px">
                    Batch ID: {escape(batch_id)} · Verify details with the employer and official authorities.
                  </td>
                </tr>
              </table>
            </td>
          </tr>
        </table>
      </body>
    </html>
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
