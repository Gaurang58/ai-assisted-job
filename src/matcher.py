import re
from typing import Dict

from src.sponsorship import (
    enrich_jobs_with_sponsorship,
    is_recruiter_company,
    sponsorship_points,
)


def clean(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").lower()).strip()


def contains_any(text: str, terms: list[str]) -> bool:
    text = clean(text)
    return any(term in text for term in terms)


BLOCK_TERMS = [
    "senior",
    "principal",
    "lead",
    "manager",
    "director",
    "staff engineer",
    "architect",
    "consultant",
    "support engineer",
    "it support",
    "data engineer",
    "data analyst",
    "business analyst",
    "cad",
    "embedded",
    "c#",
    ".net",
    "php",
    "wordpress",
]

ALLOWED_PATTERNS = [
    "junior software engineer",
    "software engineer",
    "software developer",
    "junior developer",
    "graduate software engineer",
    "graduate developer",
    "devops engineer",
    "junior devops engineer",
    "cloud engineer",
    "junior cloud engineer",
    "site reliability engineer",
    "sre",
    "node.js developer",
    "node developer",
    "javascript developer",
    "react developer",
    "frontend developer",
    "front end developer",
    "full stack developer",
    "mern",
]

CORE_STACK = [
    "javascript",
    "node.js",
    "nodejs",
    "node",
    "react",
    "rest api",
    "docker",
    "kubernetes",
    "aws",
    "azure",
    "terraform",
    "ci/cd",
    "github actions",
    "gitlab ci",
    "sql",
]


def salary_score(job: Dict, profile: dict):
    salary_min = job.get("salary_min")
    salary_max = job.get("salary_max")

    if not salary_min and not salary_max:
        return -10, ["No salary info"]

    lower = salary_min or salary_max
    upper = salary_max or salary_min
    min_target = profile["salary"]["min"]

    if upper < min_target:
        return -999, ["Salary below minimum"]

    if lower > 55000:
        return -999, ["Salary too high for target level"]

    if upper > 55000:
        return -30, ["Salary partly above target"]

    return 25, ["Salary in range"]


def stack_score(text: str):
    text = clean(text)
    hits = []
    canonical_seen = set()

    aliases = {
        "node.js": "node",
        "nodejs": "node",
        "node": "node",
    }

    for skill in CORE_STACK:
        if skill in text:
            canonical = aliases.get(skill, skill)
            if canonical not in canonical_seen:
                canonical_seen.add(canonical)
                hits.append(canonical)

    score = len(hits) * 10
    reasons = []

    if hits:
        reasons.append("Stack: " + ", ".join(hits[:5]))

    if len(hits) >= 3:
        score += 20
        reasons.append("Strong stack match")

    if len(hits) == 0:
        score -= 40
        reasons.append("No relevant stack")

    return score, reasons


def score_job(job: Dict, profile: dict) -> Dict:
    title = clean(job.get("title", ""))
    desc = clean(job.get("description", ""))
    company = clean(job.get("company", ""))
    text = f"{title} {company} {desc}"

    score = 0
    reasons = []

    if contains_any(title, BLOCK_TERMS):
        job.update(
            {
                "score": -999,
                "match_reasons": ["Blocked role"],
                "sponsorship_status": "SKIPPED",
            }
        )
        return job

    if not contains_any(title, ALLOWED_PATTERNS):
        job.update(
            {
                "score": -999,
                "match_reasons": ["Not target role"],
                "sponsorship_status": "SKIPPED",
            }
        )
        return job

    score += 50
    reasons.append("Target role match")

    if contains_any(title, ["junior", "graduate", "entry", "early career"]):
        score += 25
        reasons.append("Junior-friendly")

    sal_score, sal_reasons = salary_score(job, profile)
    if sal_score == -999:
        job.update(
            {
                "score": -999,
                "match_reasons": sal_reasons,
                "sponsorship_status": "SKIPPED",
            }
        )
        return job

    score += sal_score
    reasons.extend(sal_reasons)

    stack_points, stack_reasons = stack_score(text)
    score += stack_points
    reasons.extend(stack_reasons)

    recruiter_flag = is_recruiter_company(company)
    if recruiter_flag:
        score -= 25
        reasons.append("Recruiter/agency listing")

    sponsorship_status = job.get("sponsorship_status", "UNKNOWN")
    sponsorship_reason = job.get("sponsorship_reason", "")
    score += sponsorship_points(sponsorship_status)

    if sponsorship_status == "CONFIRMED":
        reasons.append("UK sponsor confirmed")
    elif sponsorship_status == "LIKELY":
        reasons.append("Sponsorship likely")
    elif sponsorship_status == "NO":
        reasons.append("No sponsorship")

    # Recruiter + sponsor should not outrank direct employers too easily
    if recruiter_flag and sponsorship_status == "LIKELY":
        score -= 20
        reasons.append("Recruiter sponsorship downgraded")

    # If there is no stack match and not junior, push it down harder
    if "No relevant stack" in reasons and not contains_any(
        title, ["junior", "graduate", "entry", "early career"]
    ):
        score -= 15

    # If there is no stack match and sponsorship is only likely, push down more
    if "No relevant stack" in reasons and sponsorship_status == "LIKELY":
        score -= 10

    job.update(
        {
            "score": score,
            "match_reasons": reasons[:8],
            "sponsorship_reason": sponsorship_reason,
        }
    )
    return job


def rank_jobs(jobs: list[Dict], profile: dict):
    sponsored_jobs = enrich_jobs_with_sponsorship(jobs, profile)
    scored = [score_job(job, profile) for job in sponsored_jobs]

    filtered = [
        job
        for job in scored
        if job.get("score", 0) >= 60
        and job.get("score") != -999
        and job.get("sponsorship_status") != "NO"
    ]

    return sorted(filtered, key=lambda item: item["score"], reverse=True)