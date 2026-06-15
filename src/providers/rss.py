from __future__ import annotations

import logging
from typing import Any

import feedparser
import requests

from src.config import AppConfig
from src.models import Job
from src.normalization import normalize_location, normalize_salary, parse_datetime, strip_html
from src.providers.base import retrying_session

LOGGER = logging.getLogger(__name__)


def _company(entry: dict[str, Any], title: str) -> str:
    if entry.get("author"):
        return str(entry["author"]).strip()
    source = entry.get("source")
    if isinstance(source, dict) and source.get("title"):
        return str(source["title"]).strip()
    parts = [part.strip() for part in title.split(" - ") if part.strip()]
    if len(parts) >= 2:
        return parts[-1]
    colon_parts = [part.strip() for part in title.split(":", 1)]
    return colon_parts[0] if len(colon_parts) == 2 else "Unknown"


def _location(entry: dict[str, Any], description: str) -> str:
    for field in ("location", "job_location"):
        if entry.get(field):
            return str(entry[field]).strip()
    tags = entry.get("tags") or []
    location_terms = []
    for tag in tags:
        term = tag.get("term") if isinstance(tag, dict) else None
        if term:
            location_terms.append(str(term))
    candidates = " ".join(location_terms)
    country, _, city, remote = normalize_location(candidates)
    if country or city or remote in {"remote", "remote_country_restricted", "hybrid"}:
        return candidates
    country, _, city, remote = normalize_location(description)
    return description if country or city or remote in {
        "remote", "remote_country_restricted", "hybrid"
    } else ""


def normalize_rss_job(entry: dict[str, Any], feed_url: str) -> Job:
    title = str(entry.get("title") or "").strip()
    description = strip_html(str(entry.get("summary") or entry.get("description") or ""))
    location_raw = _location(entry, description)
    country_code, country_name, city, remote_type = normalize_location(
        location_raw,
        remote_hint="remote" in f"{title} {description}".lower(),
    )
    salary = normalize_salary(None, None, None, "unknown", country_code)
    link = str(entry.get("link") or "")
    return Job(
        source="rss",
        source_country=None,
        external_id=str(entry.get("id") or link or title),
        search_query="rss",
        title=title,
        company=_company(entry, title),
        description=description,
        url=link,
        location_raw=location_raw,
        country_code=country_code,
        country_name=country_name,
        city=city,
        remote_type=remote_type,
        remote_countries=[country_code] if remote_type == "remote_country_restricted" and country_code else [],
        created_at=parse_datetime(entry.get("published") or entry.get("updated")),
        salary_min=salary[0],
        salary_max=salary[1],
        salary_currency=salary[2],
        salary_period=salary[3],
        annual_salary_min_local=salary[4],
        annual_salary_max_local=salary[5],
        metadata={"rss_feed": feed_url},
    )


class RssProvider:
    name = "rss"

    def __init__(self, session: requests.Session | None = None) -> None:
        self.session = session or retrying_session()

    def fetch(self, config: AppConfig) -> list[Job]:
        if not config.provider(self.name).get("enabled", True):
            return []
        jobs: list[Job] = []
        for feed_url in config.data["search"].get("rss_feeds", []):
            try:
                response = self.session.get(feed_url, timeout=20)
                response.raise_for_status()
                feed = feedparser.parse(response.content)
                if getattr(feed, "bozo", False) and not feed.entries:
                    raise ValueError(str(getattr(feed, "bozo_exception", "malformed feed")))
                jobs.extend(normalize_rss_job(entry, feed_url) for entry in feed.entries)
                LOGGER.info("provider=rss feed=%s raw_count=%d", feed_url, len(feed.entries))
            except (requests.RequestException, ValueError, AttributeError) as exc:
                LOGGER.warning("provider=rss feed=%s failed=%s", feed_url, exc)
        return jobs
