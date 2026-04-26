# AI-assisted Job Search

A reliable MVP job-search automation for Software Engineering, DevOps, Cloud, React, Node.js, and SRE roles.

## What it does

1. Fetches jobs from Adzuna.
2. Normalizes job data.
3. Removes duplicates.
4. Scores jobs against your profile.
5. Checks visa sponsorship wording.
6. Saves seen jobs in SQLite.
7. Emails a ranked HTML report.
8. Can run daily with GitHub Actions.

## Setup locally

```bash
python -m venv .venv
source .venv/bin/activate  # Mac/Linux
# .venv\Scripts\activate   # Windows PowerShell
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env`:

```env
ADZUNA_APP_ID=your_adzuna_app_id
ADZUNA_APP_KEY=your_adzuna_app_key
EMAIL_USER=gaurangjagtap2001@gmail.com
EMAIL_PASS=your_gmail_app_password
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
```

Run:

```bash
python -m src.main
```

Open the generated report:

```text
exports/latest_report.html
```

## GitHub Actions setup

Add these repository secrets:

- `ADZUNA_APP_ID`
- `ADZUNA_APP_KEY`
- `EMAIL_USER`
- `EMAIL_PASS`

The workflow runs every day at 07:00 UTC and can also be started manually from the GitHub Actions tab.

## Next improvements

- Add Reed API.
- Add company career pages.
- Add stronger sponsorship validation.
- Add application tracker UI.
- Add AI-generated job summaries.
- Add CV and cover-letter tailoring.
