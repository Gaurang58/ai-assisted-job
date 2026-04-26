import os
from typing import Dict, List

import feedparser
import requests

ADZUNA_ENDPOINT = "https://api.adzuna.com/v1/api/jobs/{country}/search/1"
REED_SEARCH_ENDPOINT = "https://www.reed.co.uk/api/1.0/search"


def fetch_jobs(profile: dict) -> List[Dict]:
    jobs: List[Dict] = []
    jobs.extend(fetch_adzuna_jobs(profile))
    jobs.extend(fetch_reed_jobs(profile))
    jobs.extend(fetch_rss_jobs(profile))
    return jobs


# ----------------------------
# ADZUNA
# ----------------------------
def fetch_adzuna_jobs(profile: dict) -> List[Dict]:
    app_id = os.getenv("ADZUNA_APP_ID")
    app_key = os.getenv("ADZUNA_APP_KEY")
    if not app_id or not app_key:
        raise RuntimeError("Missing ADZUNA_APP_ID or ADZUNA_APP_KEY in environment.")

    jobs: List[Dict] = []
    countries = profile["search"].get("countries", ["gb"])
    queries = profile.get("queries", [])
    results_per_query = int(profile["search"].get("results_per_query", 50))

    for country in countries:
        for query in queries:
            params = {
                "app_id": app_id,
                "app_key": app_key,
                "what": query,
                "results_per_page": results_per_query,
                "content-type": "application/json",
                "sort_by": "date",
            }
            response = requests.get(
                ADZUNA_ENDPOINT.format(country=country),
                params=params,
                timeout=30,
            )
            response.raise_for_status()
            payload = response.json()

            for item in payload.get("results", []):
                jobs.append(normalize_adzuna_job(item, country, query))

    return jobs


def normalize_adzuna_job(item: Dict, country: str, query: str) -> Dict:
    company = item.get("company") or {}
    location = item.get("location") or {}
    return {
        "source": "adzuna",
        "source_country": country,
        "search_query": query,
        "external_id": str(item.get("id", "")),
        "title": item.get("title", "").strip(),
        "company": company.get("display_name", "Unknown").strip(),
        "location": location.get("display_name", "").strip(),
        "description": item.get("description", "").strip(),
        "url": item.get("redirect_url", ""),
        "created": item.get("created", ""),
        "salary_min": item.get("salary_min"),
        "salary_max": item.get("salary_max"),
        "currency": "GBP" if country == "gb" else "EUR",
    }


# ----------------------------
# REED
# ----------------------------
def fetch_reed_jobs(profile: dict) -> List[Dict]:
    reed_api_key = os.getenv("REED_API_KEY")
    if not reed_api_key:
        return []

    jobs: List[Dict] = []
    queries = profile.get("queries", [])
    results_per_query = min(int(profile["search"].get("results_per_query", 50)), 100)
    min_salary = int(profile["salary"]["min"])
    max_salary = int(profile["salary"]["max"])

    locations = profile["search"].get(
        "reed_locations",
        ["London", "Manchester", "Birmingham", "Leeds", "Bristol"],
    )

    session = requests.Session()
    session.auth = (reed_api_key, "")

    for query in queries:
        for location in locations:
            params = {
                "keywords": query,
                "locationName": location,
                "minimumSalary": min_salary,
                "maximumSalary": max_salary,
                "resultsToTake": results_per_query,
            }

            try:
                response = session.get(REED_SEARCH_ENDPOINT, params=params, timeout=30)
                response.raise_for_status()
                payload = response.json()

                for item in payload.get("results", []):
                    jobs.append(normalize_reed_job(item, query, location))
            except requests.RequestException:
                continue

    return jobs


def normalize_reed_job(item: Dict, query: str, location: str) -> Dict:
    url = item.get("jobUrl") or item.get("externalUrl") or ""
    return {
        "source": "reed",
        "source_country": "gb",
        "search_query": query,
        "external_id": str(item.get("jobId", "")),
        "title": (item.get("jobTitle") or "").strip(),
        "company": (item.get("employerName") or "Unknown").strip(),
        "location": (item.get("locationName") or location or "").strip(),
        "description": (item.get("jobDescription") or item.get("description") or "").strip(),
        "url": url,
        "created": item.get("date") or item.get("expirationDate") or "",
        "salary_min": item.get("minimumSalary") or item.get("yearlyMinimumSalary"),
        "salary_max": item.get("maximumSalary") or item.get("yearlyMaximumSalary"),
        "currency": item.get("currency") or "GBP",
    }


# ----------------------------
# RSS
# ----------------------------
def fetch_rss_jobs(profile: dict) -> List[Dict]:
    jobs: List[Dict] = []
    rss_urls = profile["search"].get("rss_feeds", [])
    if not rss_urls:
        return jobs

    for feed_url in rss_urls:
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries:
                jobs.append(normalize_rss_job(entry, feed_url))
        except Exception:
            continue

    return jobs


def normalize_rss_job(entry: Dict, feed_url: str) -> Dict:
    title = (entry.get("title") or "").strip()
    summary = (entry.get("summary") or entry.get("description") or "").strip()
    link = entry.get("link") or ""
    published = entry.get("published") or entry.get("updated") or ""

    company = extract_company_from_rss(entry, title)
    location = extract_location_from_rss(entry, summary)

    return {
        "source": "rss",
        "source_country": "gb",
        "search_query": "rss",
        "external_id": str(entry.get("id") or link or title),
        "title": title,
        "company": company,
        "location": location,
        "description": summary,
        "url": link,
        "created": published,
        "salary_min": None,
        "salary_max": None,
        "currency": "GBP",
        "rss_feed": feed_url,
    }


def extract_company_from_rss(entry: Dict, title: str) -> str:
    if entry.get("author"):
        return str(entry.get("author")).strip()

    source = entry.get("source")
    if isinstance(source, dict) and source.get("title"):
        return str(source.get("title")).strip()

    parts = [p.strip() for p in title.split(" - ") if p.strip()]
    if len(parts) >= 2:
        return parts[-1]

    return "Unknown"


def extract_location_from_rss(entry: Dict, summary: str) -> str:
    tags = entry.get("tags", [])
    for tag in tags:
        term = tag.get("term")
        if term:
            return str(term).strip()

    summary_lower = summary.lower()
    common_locations = [
        "london",
        "manchester",
        "birmingham",
        "leeds",
        "bristol",
        "glasgow",
        "edinburgh",
        "sheffield",
        "liverpool",
        "uk",
        "remote",
    ]
    for loc in common_locations:
        if loc in summary_lower:
            return loc.title()

    return ""