from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.config import load_config
from src.models import Job


@pytest.fixture
def config():
    return load_config()


@pytest.fixture
def job_factory():
    def make(**overrides):
        values = {
            "source": "test",
            "source_country": "de",
            "external_id": "1",
            "search_query": "software engineer",
            "title": "Junior Software Engineer",
            "company": "Example Technology",
            "description": "JavaScript Node.js React Docker. Visa sponsorship available.",
            "url": "https://example.test/jobs/1",
            "location_raw": "Berlin, Germany",
            "country_code": "de",
            "country_name": "Germany",
            "city": "Berlin",
            "remote_type": "hybrid",
            "created_at": datetime(2026, 6, 10, tzinfo=timezone.utc),
            "salary_min": 50000.0,
            "salary_max": 70000.0,
            "salary_currency": "EUR",
            "salary_period": "annual",
            "annual_salary_min_local": 50000.0,
            "annual_salary_max_local": 70000.0,
        }
        values.update(overrides)
        return Job(**values)
    return make
