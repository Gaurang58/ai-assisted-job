from src.normalization import normalize_location, normalize_salary
from src.providers.adzuna import AdzunaProvider, normalize_adzuna_job
from src.providers.arbeitnow import normalize_arbeitnow_job
from src.providers.rss import normalize_rss_job


def test_adzuna_normalisation_by_country():
    item = {
        "id": 42, "title": "Softwareentwickler", "company": {"display_name": "Acme"},
        "location": {"display_name": "Berlin"}, "description": "<b>Node.js</b>",
        "redirect_url": "https://example.test/42", "salary_min": 40000,
    }
    job = normalize_adzuna_job(item, "de", "software engineer")
    assert (job.country_code, job.city, job.salary_currency) == ("de", "Berlin", "EUR")
    assert job.description == "Node.js"


def test_adzuna_uses_source_currency():
    item = {
        "id": 1, "title": "Software Engineer", "company": {}, "location": {},
        "salary_min": 10, "salary_currency": "USD",
    }
    assert normalize_adzuna_job(item, "ie", "software").salary_currency == "USD"


def test_rss_unknown_country_is_not_uk():
    job = normalize_rss_job(
        {"title": "Software Engineer - Acme", "summary": "Build APIs", "link": "https://x"},
        "https://feed",
    )
    assert job.country_code is None
    assert job.source_country is None


def test_remote_without_country_stays_global():
    job = normalize_rss_job(
        {"title": "Remote Software Engineer", "summary": "This role is fully remote"},
        "https://feed",
    )
    assert job.country_code is None
    assert job.remote_type == "remote"


def test_remote_country_restriction():
    country, _, city, remote = normalize_location("Remote - Dublin, Ireland")
    assert (country, city, remote) == ("ie", "Dublin", "remote_country_restricted")


def test_currency_mapping_and_annualisation():
    salary = normalize_salary(4000, 5000, None, "monthly", "nl")
    assert salary == (4000.0, 5000.0, "EUR", "monthly", 48000.0, 60000.0)


def test_unknown_salary_period_is_not_annualised():
    salary = normalize_salary(50, None, "EUR", "hourly-ish", "de")
    assert salary[3] == "unknown"
    assert salary[4] is None


def test_arbeitnow_does_not_assume_germany():
    job = normalize_arbeitnow_job({
        "slug": "dublin-role", "title": "Software Engineer", "company_name": "Acme",
        "location": "Dublin, Ireland", "description": "APIs", "url": "https://x",
        "remote": False,
    })
    assert job.country_code == "ie"


class FakeResponse:
    def raise_for_status(self):
        return None

    def json(self):
        return {"results": []}


class FakeSession:
    def __init__(self):
        self.urls = []

    def get(self, url, **kwargs):
        self.urls.append(url)
        return FakeResponse()


def test_adzuna_http_adapter_queries_all_phase_one_countries(config, monkeypatch):
    monkeypatch.setenv("ADZUNA_APP_ID", "id")
    monkeypatch.setenv("ADZUNA_APP_KEY", "key")
    config.data["queries"] = ["software engineer"]
    config.data["providers"]["adzuna"]["request_delay_seconds"] = 0
    session = FakeSession()
    AdzunaProvider(session).fetch(config)
    assert {url.split("/jobs/")[1].split("/")[0] for url in session.urls} == {"gb", "de", "nl", "ie"}
