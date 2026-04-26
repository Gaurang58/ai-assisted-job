import hashlib
import re
from typing import Dict, List


RECRUITER_WORDS = {
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
}


def clean_text(value: str) -> str:
    value = (value or "").lower()
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def normalize_company(value: str) -> str:
    text = clean_text(value)
    parts = [p for p in text.split() if p not in RECRUITER_WORDS]
    return " ".join(parts).strip() or text


def normalize_title(value: str) -> str:
    text = clean_text(value)

    replacements = {
        "node js": "nodejs",
        "node js developer": "nodejs developer",
        "front end": "frontend",
        "full stack": "fullstack",
        "dev ops": "devops",
        "site reliability engineer": "sre",
        "software developer": "software engineer",
    }

    for old, new in replacements.items():
        text = text.replace(old, new)

    # remove noisy location/salary fragments from titles
    text = re.sub(r"\b(london|manchester|birmingham|sheffield|uk|hybrid|remote)\b", " ", text)
    text = re.sub(r"\b\d{2,3}k\b", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def salary_bucket(job: Dict) -> str:
    low = job.get("salary_min")
    high = job.get("salary_max")
    if low is None and high is None:
        return "none"

    low = int(low or high or 0)
    high = int(high or low or 0)
    return f"{low//5000}-{high//5000}"


def make_job_id(job: Dict) -> str:
    if job.get("external_id"):
        raw = f"{job.get('source')}|{job.get('external_id')}"
    else:
        raw = "|".join(
            [
                normalize_title(job.get("title", "")),
                normalize_company(job.get("company", "")),
                clean_text(job.get("location", "")),
            ]
        )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def make_soft_key(job: Dict) -> str:
    return "|".join(
        [
            normalize_title(job.get("title", "")),
            normalize_company(job.get("company", "")),
            salary_bucket(job),
        ]
    )


def is_better_job(candidate: Dict, existing: Dict) -> bool:
    candidate_score = candidate.get("score", 0)
    existing_score = existing.get("score", 0)

    if candidate_score != existing_score:
        return candidate_score > existing_score

    candidate_sponsorship = candidate.get("sponsorship_status", "UNKNOWN")
    existing_sponsorship = existing.get("sponsorship_status", "UNKNOWN")
    order = {"CONFIRMED": 3, "LIKELY": 2, "UNKNOWN": 1, "NO": 0}
    if order.get(candidate_sponsorship, 0) != order.get(existing_sponsorship, 0):
        return order.get(candidate_sponsorship, 0) > order.get(existing_sponsorship, 0)

    candidate_has_url = bool(candidate.get("url"))
    existing_has_url = bool(existing.get("url"))
    return candidate_has_url and not existing_has_url


def dedupe_jobs(jobs: List[Dict]) -> List[Dict]:
    exact_seen = set()
    unique: List[Dict] = []
    soft_index: Dict[str, int] = {}

    for job in jobs:
        job_id = make_job_id(job)

        if job_id in exact_seen:
            continue

        exact_seen.add(job_id)
        job["job_id"] = job_id

        soft_key = make_soft_key(job)
        if soft_key in soft_index:
            existing_idx = soft_index[soft_key]
            existing_job = unique[existing_idx]
            if is_better_job(job, existing_job):
                unique[existing_idx] = job
            continue

        soft_index[soft_key] = len(unique)
        unique.append(job)

    return unique