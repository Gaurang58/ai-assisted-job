# AI-assisted Job Search

Phase One searches and ranks software, DevOps, cloud, frontend, full-stack and SRE
roles in the United Kingdom, Germany, the Netherlands and Ireland.

## Architecture

- `src/providers/`: Adzuna (`gb`, `de`, `nl`, `ie`), Reed (`gb` only), RSS and Arbeitnow adapters.
- `src/normalization.py`: country, city, remote and local-salary normalization.
- `src/eligibility/`: one evidence checker per Phase One country.
- `src/scoring.py` and `src/dedupe.py`: configurable relevance scoring and two-stage deduplication.
- `src/storage/`: SQLite for local state and Google Sheets for durable Actions state/tracking.
- `src/main.py`: fetch → normalize → dedupe → enrich → rank → persist → email transaction.

Register presence is employer-level evidence only. The project does not call a
vacancy a confirmed sponsor and does not provide legal advice or guarantee a visa outcome.

## Local setup

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
```

Configure `config/profile.yaml` for roles, skills, countries and salary preferences.
Immigration reference data and effective dates live in `config/eligibility_rules.yaml`.

Run without external writes:

```bash
python -m src.main --dry-run
```

Other modes:

```bash
python -m src.main             # email + Google Sheets + local SQLite
python -m src.main --no-email  # state/Sheets processing, no SMTP or tracker insertion
python -m src.main --no-sheets # email + local SQLite only
pytest -q
```

The generated local report is `exports/latest_report.html`.

## Environment variables

- `ADZUNA_APP_ID`, `ADZUNA_APP_KEY`
- `REED_API_KEY` (optional)
- `EMAIL_USER`, `EMAIL_PASS`, `EMAIL_RECIPIENT`
- `SMTP_HOST`, `SMTP_PORT` (optional; Gmail defaults are used)
- `GOOGLE_SHEET_ID`, `GOOGLE_SERVICE_ACCOUNT_JSON`

`GOOGLE_SERVICE_ACCOUNT_JSON` must contain the complete JSON document as one
environment variable or GitHub secret. It is parsed in memory and never logged.

## Google Sheets setup

1. Create a Google Cloud project and enable the Google Sheets API.
2. Create a service account and JSON key.
3. Create a spreadsheet and copy its ID from the URL.
4. Share the spreadsheet with the service-account `client_email` as an editor.
5. Add `GOOGLE_SHEET_ID` and the complete JSON key as `GOOGLE_SERVICE_ACCOUNT_JSON`.

The application creates `Jobs Tracker`, `Bot State` and `Email Log` when absent.
For an existing formatted tracker, keep the exact documented headers. Automated
upserts update bot-managed columns and preserve non-empty user-editable columns.

## GitHub Actions

Add all environment variables above as repository secrets, including the optional
Reed key if Reed should run. The workflow runs tests before the scheduled/manual
search, uses pip caching, prevents overlapping runs and treats Sheets as durable state.

## Migration from the UK-only version

The first local run migrates the existing SQLite `jobs` table in place. The committed
sponsor-register cache has been removed; registers are cached as generated runtime data.
Move any personal email from old `config/profile.yaml` copies into `EMAIL_RECIPIENT`.
Create and share the Google Sheet before running the default command in Actions.

## Troubleshooting

- `configuration error`: check YAML structure and Phase One country codes.
- Google authentication errors: confirm the JSON secret is complete and the sheet is shared.
- No Adzuna results: confirm both Adzuna credentials; other providers continue independently.
- SMTP failure: the batch is marked failed, jobs remain unemailed, and a retry is safe.
- Missing registry: eligibility degrades to vacancy evidence instead of terminating the run.
