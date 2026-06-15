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
    "strong": ("#166534", "#dcfce7", "#bbf7d0"),
    "possible": ("#1d4ed8", "#dbeafe", "#bfdbfe"),
    "unknown": ("#4b5563", "#f3f4f6", "#e5e7eb"),
    "unlikely": ("#b91c1c", "#fee2e2", "#fecaca"),
}


def format_salary(job: Job) -> str:
    if job.salary_min is None and job.salary_max is None:
        return "Not listed"
    values = [value for value in (job.salary_min, job.salary_max) if value is not None]
    amount = f"{values[0]:,.0f}" if len(values) == 1 else f"{values[0]:,.0f} - {values[-1]:,.0f}"
    return f"{job.salary_currency or ''} {amount} / {job.salary_period or 'unknown'}".strip()


def _display_remote_type(value: str) -> str:
    labels = {
        "onsite": "On-site",
        "hybrid": "Hybrid",
        "remote": "Remote",
        "remote_country_restricted": "Remote, country restricted",
        "unknown": "Not specified",
    }
    return labels.get(value, value.replace("_", " ").title())


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


def _metadata_cell(label: str, value: str) -> str:
    return f"""
    <td width="50%" valign="top" style="padding:0 12px 12px 0">
      <div style="font-size:11px;line-height:16px;color:#6b7280;text-transform:uppercase;
                  letter-spacing:.5px;font-weight:700">{escape(label)}</div>
      <div style="font-size:14px;line-height:20px;color:#111827;font-weight:600">
        {escape(value or "Not specified")}
      </div>
    </td>
    """


def _job_card(job: Job, number: int) -> str:
    result = job.work_authorisation_result or "unknown"
    auth_text, auth_background, auth_border = AUTH_STYLES.get(result, AUTH_STYLES["unknown"])
    created = job.created_at.date().isoformat() if job.created_at else "Not listed"
    country = job.country_name or COUNTRY_LABELS["unknown"]
    location = ", ".join(value for value in (job.city, country) if value)
    reasons = " | ".join(job.match_reasons) or "Profile match"
    application_link = escape(job.url, quote=True)
    return f"""
    <tr>
      <td style="padding:0 0 16px">
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0"
               style="width:100%;border:1px solid #dbe3ef;border-collapse:separate;
                      border-spacing:0;background:#ffffff;border-radius:10px">
          <tr>
            <td style="padding:20px 20px 14px">
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
                <tr>
                  <td width="44" valign="top" style="padding-right:12px">
                    <div style="width:34px;height:34px;line-height:34px;text-align:center;
                                border-radius:17px;background:#e8eefc;color:#1e40af;
                                font-size:13px;font-weight:700">{number}</div>
                  </td>
                  <td valign="top">
                    <a href="{application_link}" style="font-size:18px;line-height:24px;
                       color:#153e75;font-weight:700;text-decoration:none">
                      {escape(job.title)}
                    </a>
                    <div style="padding-top:4px;font-size:14px;line-height:20px;
                                color:#374151;font-weight:600">{escape(job.company)}</div>
                    <div style="padding-top:8px">
                      <span style="display:inline-block;padding:5px 9px;border-radius:14px;
                                 border:1px solid {auth_border};background:{auth_background};
                                 color:{auth_text};font-size:11px;line-height:14px;
                                 font-weight:700;text-transform:uppercase">
                        Work authorisation: {escape(result)}
                      </span>
                    </div>
                  </td>
                </tr>
              </table>
            </td>
          </tr>
          <tr>
            <td style="padding:0 20px">
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0"
                     style="border-top:1px solid #eef2f7;padding-top:14px">
                <tr>
                  {_metadata_cell("Location", location)}
                  {_metadata_cell("Work style", _display_remote_type(job.remote_type))}
                </tr>
                <tr>
                  {_metadata_cell("Salary", format_salary(job))}
                  {_metadata_cell("Posted", created)}
                </tr>
                <tr>
                  {_metadata_cell("Source", job.source.title())}
                  {_metadata_cell("Match score", f"{job.match_score}/100")}
                </tr>
              </table>
            </td>
          </tr>
          <tr>
            <td style="padding:2px 20px 16px">
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0"
                     style="background:#f8fafc;border-collapse:separate;border-spacing:0;
                            border-radius:8px">
                <tr>
                  <td style="padding:12px 14px">
                    <div style="font-size:11px;line-height:16px;color:#6b7280;
                                text-transform:uppercase;letter-spacing:.5px;font-weight:700">
                      Work-authorisation evidence
                    </div>
                    <div style="padding-top:4px;font-size:13px;line-height:19px;color:#374151">
                      <strong>Employer:</strong> {escape(job.employer_evidence or "No employer evidence")}
                    </div>
                    <div style="padding-top:3px;font-size:13px;line-height:19px;color:#374151">
                      <strong>Vacancy:</strong> {escape(job.vacancy_evidence or "Not mentioned")}
                    </div>
                    <div style="padding-top:3px;font-size:13px;line-height:19px;color:#374151">
                      <strong>Permit route:</strong> {escape(job.permit_route or "Not identified")}
                    </div>
                  </td>
                </tr>
              </table>
            </td>
          </tr>
          <tr>
            <td style="padding:0 20px 16px">
              <div style="font-size:11px;line-height:16px;color:#6b7280;text-transform:uppercase;
                          letter-spacing:.5px;font-weight:700">Why this matched</div>
              <div style="padding-top:4px;font-size:13px;line-height:19px;color:#374151">
                {escape(reasons)}
              </div>
            </td>
          </tr>
          <tr>
            <td style="padding:0 20px 20px">
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
                <tr>
                  <td align="center" bgcolor="#1d4ed8" style="border-radius:6px">
                    <a href="{application_link}" style="display:block;padding:11px 16px;
                       color:#ffffff;font-size:14px;line-height:18px;font-weight:700;
                       text-decoration:none">View job and apply</a>
                  </td>
                </tr>
              </table>
            </td>
          </tr>
        </table>
      </td>
    </tr>
    """


def render_html_report(jobs: list[Job], profile: dict, batch_id: str) -> str:
    groups = _group_jobs(jobs)
    summary = "".join(
        f"""
        <td align="center" style="padding:8px 5px">
          <div style="font-size:20px;line-height:24px;color:#153e75;font-weight:700">{len(items)}</div>
          <div style="font-size:11px;line-height:15px;color:#6b7280">
            {escape(COUNTRY_LABELS[code])}
          </div>
        </td>
        """
        for code, items in groups
    )
    sections = []
    number = 1
    for code, country_jobs in groups:
        label = COUNTRY_LABELS[code]
        sections.append(
            f"""
            <tr>
              <td style="padding:24px 0 12px">
                <table role="presentation" width="100%" cellpadding="0" cellspacing="0"
                       style="background:#153e75;border-collapse:separate;border-spacing:0;
                              border-radius:8px">
                  <tr>
                    <td style="padding:12px 16px;color:#ffffff;font-size:17px;
                               line-height:22px;font-weight:700">{escape(label)}</td>
                    <td align="right" style="padding:12px 16px;color:#dbeafe;
                                            font-size:13px;line-height:22px">
                      {len(country_jobs)} {"job" if len(country_jobs) == 1 else "jobs"}
                    </td>
                  </tr>
                </table>
              </td>
            </tr>
            """
        )
        for job in country_jobs:
            sections.append(_job_card(job, number))
            number += 1

    body = "".join(sections) if sections else """
      <tr><td style="padding:32px;text-align:center;color:#6b7280">
        No new matching jobs were selected.
      </td></tr>
    """
    return f"""
    <!doctype html>
    <html>
      <head>
        <meta name="viewport" content="width=device-width,initial-scale=1">
        <meta name="x-apple-disable-message-reformatting">
      </head>
      <body style="margin:0;padding:0;background:#f3f6fa;font-family:Arial,Helvetica,sans-serif">
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0"
               style="width:100%;background:#f3f6fa">
          <tr>
            <td align="center" style="padding:24px 12px">
              <table role="presentation" width="680" cellpadding="0" cellspacing="0"
                     style="width:100%;max-width:680px">
                <tr>
                  <td style="padding:24px;background:#153e75;border-radius:12px 12px 0 0">
                    <div style="font-size:12px;line-height:18px;color:#bfdbfe;
                                text-transform:uppercase;letter-spacing:1px;font-weight:700">
                      AI-assisted job search
                    </div>
                    <div style="padding-top:5px;font-size:27px;line-height:34px;
                                color:#ffffff;font-weight:700">Your latest job matches</div>
                    <div style="padding-top:8px;font-size:14px;line-height:21px;color:#dbeafe">
                      {len(jobs)} ranked jobs for {escape(profile["profile"]["name"])}
                    </div>
                  </td>
                </tr>
                <tr>
                  <td style="padding:16px 18px;background:#ffffff;border-bottom:1px solid #e5e7eb">
                    <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
                      <tr>{summary}</tr>
                    </table>
                  </td>
                </tr>
                <tr>
                  <td style="padding:14px 18px;background:#fff7ed;color:#7c2d12;
                             font-size:12px;line-height:18px;border-bottom:1px solid #fed7aa">
                    Work-authorisation results are evidence-based guidance, not legal advice
                    or a guaranteed visa outcome.
                  </td>
                </tr>
                <tr>
                  <td style="padding:0 18px 22px;background:#ffffff">
                    <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
                      {body}
                    </table>
                  </td>
                </tr>
                <tr>
                  <td align="center" style="padding:16px;background:#e8eef7;color:#64748b;
                                           font-size:11px;line-height:17px;
                                           border-radius:0 0 12px 12px">
                    Batch ID: {escape(batch_id)}<br>
                    Generated automatically. Always verify vacancy and immigration details
                    with the employer and official authorities.
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
