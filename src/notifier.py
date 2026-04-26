import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from html import escape
from typing import Dict, List


RECRUITER_WORDS = [
    "recruitment",
    "recruiter",
    "search",
    "selection",
    "staffing",
    "talent",
    "resourcing",
    "consulting",
    "consultancy",
    "associates",
    "resource",
    "resources",
    "agency",
]


def is_recruiter(company: str) -> bool:
    company_l = (company or "").lower()
    return any(word in company_l for word in RECRUITER_WORDS)


def format_salary(job: Dict) -> str:
    if not (job.get("salary_min") or job.get("salary_max")):
        return "Not listed"

    currency = job.get("currency", "")
    low = job.get("salary_min")
    high = job.get("salary_max")

    if low and high:
        if float(low) == float(high):
            return f"{currency} {low:.0f}" if isinstance(low, float) else f"{currency} {low}"
        return f"{currency} {low:.0f} - {high:.0f}" if isinstance(low, float) or isinstance(high, float) else f"{currency} {low} - {high}"

    value = low or high
    return f"{currency} {value:.0f}" if isinstance(value, float) else f"{currency} {value}"


def render_html_report(jobs: List[Dict], profile: dict) -> str:
    rows = []

    for idx, job in enumerate(jobs, start=1):
        salary = format_salary(job)
        reasons = ", ".join(job.get("match_reasons", [])) or "Profile match"
        sponsorship = escape(job.get("sponsorship_status", "UNKNOWN"))
        sponsorship_reason = escape(job.get("sponsorship_reason", ""))
        company = escape(job.get("company", ""))
        recruiter_flag = "Yes" if is_recruiter(job.get("company", "")) else "No"
        url = escape(job.get("url", ""))
        title = escape(job.get("title", ""))

        rows.append(
            f"""
            <tr>
              <td>{idx}</td>
              <td><a href="{url}">{title}</a></td>
              <td>{company}</td>
              <td>{escape(job.get('location', ''))}</td>
              <td>{job.get('score', 0)}</td>
              <td><strong>{sponsorship}</strong><br><small>{sponsorship_reason}</small></td>
              <td>{escape(salary)}</td>
              <td>{recruiter_flag}</td>
              <td>{escape(reasons)}</td>
            </tr>
            """
        )

    return f"""
    <html>
    <body style="font-family: Arial, sans-serif; line-height: 1.4;">
      <h2>AI-assisted Job Search Results</h2>
      <p>Found {len(jobs)} ranked jobs for {escape(profile['profile']['name'])}.</p>
      <table border="1" cellpadding="6" cellspacing="0" style="border-collapse: collapse; width: 100%;">
        <thead>
          <tr>
            <th>#</th>
            <th>Role</th>
            <th>Company</th>
            <th>Location</th>
            <th>Score</th>
            <th>Sponsorship</th>
            <th>Salary</th>
            <th>Recruiter</th>
            <th>Why matched</th>
          </tr>
        </thead>
        <tbody>
          {''.join(rows)}
        </tbody>
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
        raise RuntimeError("Missing EMAIL_USER or EMAIL_PASS in environment.")

    message = MIMEMultipart("alternative")
    message["Subject"] = subject
    message["From"] = email_user
    message["To"] = recipient
    message.attach(MIMEText(html_body, "html"))

    with smtplib.SMTP(smtp_host, smtp_port) as server:
        server.starttls()
        server.login(email_user, email_pass)
        server.send_message(message)