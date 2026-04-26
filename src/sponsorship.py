import difflib
import io
import json
import re
from datetime import date
from pathlib import Path
from typing import Dict, Tuple

import requests

CACHE_DIR = Path("data")
CACHE_FILE = CACHE_DIR / "sponsor_register_cache.json"
CACHE_DATE_FILE = CACHE_DIR / "sponsor_register_date.txt"

UK_REGISTER_PAGE = "https://www.gov.uk/government/publications/register-of-licensed-sponsors-workers"

DEFAULT_POSITIVE = [
    "visa sponsorship available",
    "visa sponsorship provided",
    "sponsorship available",
    "we sponsor",
    "we will sponsor",
    "skilled worker visa",
    "tier 2 sponsorship",
    "certificate of sponsorship",
    "cos available",
    "sponsorship considered",
    "sponsorship is available",
    "can sponsor",
    "able to sponsor",
    "we are able to sponsor",
    "sponsorship will be provided",
    "relocation assistance",
    "international candidates welcome",
    "open to international",
    "work permit",
    "work visa",
    "sponsorship for the right candidate",
]

DEFAULT_NEGATIVE = [
    "no sponsorship",
    "unable to sponsor",
    "cannot sponsor",
    "sponsorship is not available",
    "must have right to work",
    "must already have right to work",
    "right to work required",
    "no visa sponsorship",
    "unfortunately we cannot sponsor",
    "we do not offer sponsorship",
    "we are unable to offer visa sponsorship",
    "only applicants with right to work",
    "applicants must have existing right to work",
]

RECRUITER_WORDS = {
    "recruitment",
    "recruiter",
    "associates",
    "talent",
    "consulting",
    "consultancy",
    "staffing",
    "resourcing",
    "search",
    "selection",
    "agency",
    "resource",
    "resources",
}


def clean(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").lower()).strip()


def is_recruiter_company(company: str) -> bool:
    company_l = clean(company)
    return any(word in company_l for word in RECRUITER_WORDS)


def _normalise_company(name: str) -> str:
    name = clean(name)
    suffixes = [
        " ltd",
        " limited",
        " plc",
        " llp",
        " llc",
        " inc",
        " group",
        " uk",
        " solutions",
        " services",
        " consulting",
        " consultancy",
        " technologies",
        " technology",
        " holdings",
        " holding",
        " recruitment",
        " associates",
        " agency",
    ]
    for suffix in suffixes:
        if name.endswith(suffix):
            name = name[: -len(suffix)].strip()

    name = re.sub(r"[^\w\s]", " ", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name


def _get_register_download_url() -> str:
    try:
        r = requests.get(
            UK_REGISTER_PAGE,
            timeout=20,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        r.raise_for_status()

        urls = re.findall(
            r'href="(https://assets\.publishing\.service\.gov\.uk[^"]+(?:Worker[^"]*\.xlsx|sponsor[^"]*\.xlsx|Worker[^"]*\.csv))"',
            r.text,
            re.IGNORECASE,
        )
        if urls:
            return urls[0]

        urls = re.findall(
            r'href="(https://assets\.publishing\.service\.gov\.uk[^"]+\.xlsx)"',
            r.text,
        )
        if urls:
            return urls[0]
    except Exception:
        pass

    return ""


def _download_register() -> set[str]:
    companies: set[str] = set()
    url = _get_register_download_url()
    if not url:
        return companies

    try:
        r = requests.get(url, timeout=45, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()

        try:
            import openpyxl

            wb = openpyxl.load_workbook(io.BytesIO(r.content), read_only=True)
            ws = wb.active
            for row in ws.iter_rows(min_row=2, values_only=True):
                if row and row[0]:
                    companies.add(clean(str(row[0])))
            return companies
        except Exception:
            text = r.content.decode("utf-8", errors="ignore")
            for line in text.splitlines()[1:]:
                parts = line.split(",")
                if parts and parts[0]:
                    companies.add(clean(parts[0].strip().strip('"')))
            return companies
    except Exception:
        return companies


def load_uk_register() -> set[str]:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()

    if CACHE_FILE.exists() and CACHE_DATE_FILE.exists():
        try:
            cached_date = CACHE_DATE_FILE.read_text(encoding="utf-8").strip()
            if cached_date == today:
                data = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
                return set(data.get("companies", []))
        except Exception:
            pass

    companies = _download_register()
    if companies:
        try:
            CACHE_FILE.write_text(
                json.dumps({"companies": list(companies)}),
                encoding="utf-8",
            )
            CACHE_DATE_FILE.write_text(today, encoding="utf-8")
        except Exception:
            pass

    return companies


def is_on_uk_register(
    company: str,
    register: set[str],
    threshold: float = 0.92,
) -> Tuple[bool, str, float]:
    if not company or not register:
        return False, "", 0.0

    norm_company = _normalise_company(company)
    if not norm_company:
        return False, "", 0.0

    company_words = [w for w in norm_company.split() if w not in RECRUITER_WORDS]
    if not company_words:
        return False, "", 0.0

    normalised_register = {_normalise_company(name): name for name in register}

    if norm_company in normalised_register:
        return True, normalised_register[norm_company], 1.0

    meaningful_name = " ".join(company_words)
    if len(meaningful_name) >= 10:
        for norm_reg, original in normalised_register.items():
            if meaningful_name == norm_reg:
                return True, original, 1.0
            if meaningful_name in norm_reg or norm_reg in meaningful_name:
                overlap_words = set(meaningful_name.split()) & set(norm_reg.split())
                if len(overlap_words) >= 2:
                    return True, original, 0.95

    candidates = []
    for norm_reg, original in normalised_register.items():
        reg_words = set(norm_reg.split())
        overlap = set(company_words) & reg_words
        if not overlap:
            continue

        score = difflib.SequenceMatcher(None, meaningful_name, norm_reg).ratio()
        if score >= threshold:
            candidates.append((score, original, norm_reg))

    if candidates:
        candidates.sort(reverse=True, key=lambda x: x[0])
        best_score, best_original, _ = candidates[0]
        return True, best_original, round(best_score, 2)

    return False, "", 0.0


def check_description_signals(job: Dict, profile: dict) -> Tuple[str, str]:
    text = clean(
        f"{job.get('title', '')} {job.get('company', '')} {job.get('description', '')}"
    )

    negative_terms = profile.get("visa", {}).get("negative_terms", DEFAULT_NEGATIVE)
    positive_terms = profile.get("visa", {}).get("positive_terms", DEFAULT_POSITIVE)

    for phrase in negative_terms:
        if clean(phrase) in text:
            return "NO", f'Text says: "{phrase}"'

    for phrase in positive_terms:
        if clean(phrase) in text:
            return "LIKELY", f'Text says: "{phrase}"'

    return "UNKNOWN", "No explicit sponsorship wording found"


def check_job_sponsorship(job: Dict, profile: dict, uk_register: set[str]) -> Dict:
    location = clean(job.get("location", ""))
    company = job.get("company", "")
    recruiter_flag = is_recruiter_company(company)

    uk_indicators = [
        "uk",
        "united kingdom",
        "england",
        "scotland",
        "wales",
        "london",
        "manchester",
        "birmingham",
    ]
    is_probably_uk = (
        job.get("source_country") == "gb"
        or any(x in location for x in uk_indicators)
        or not location
    )

    if is_probably_uk:
        on_register, matched_name, confidence = is_on_uk_register(company, uk_register)
        if on_register:
            if recruiter_flag:
                job["sponsorship_status"] = "LIKELY"
                job["sponsorship_reason"] = (
                    f"Recruiter company is on UK sponsor register "
                    f"(matched '{matched_name}', confidence {int(confidence * 100)}%)"
                )
            else:
                job["sponsorship_status"] = "CONFIRMED"
                job["sponsorship_reason"] = (
                    f"On UK sponsor register (matched '{matched_name}', confidence {int(confidence * 100)}%)"
                )
            return job

    status, reason = check_description_signals(job, profile)
    job["sponsorship_status"] = status
    job["sponsorship_reason"] = reason
    return job


def sponsorship_points(status: str) -> int:
    return {
        "CONFIRMED": 80,
        "LIKELY": 30,
        "UNKNOWN": 0,
        "NO": -200,
    }.get(status, 0)


def enrich_jobs_with_sponsorship(jobs: list[Dict], profile: dict) -> list[Dict]:
    register = load_uk_register()
    return [check_job_sponsorship(job, profile, register) for job in jobs]