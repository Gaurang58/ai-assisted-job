from src.eligibility.common import EligibilityEngine
from src.eligibility.netherlands import download_nl_register
from src.eligibility.utils import Registry
from src.scoring import score_job


def engine(config, *, uk=None, nl=None):
    return EligibilityEngine(
        config, uk_registry=Registry(set(uk or [])), nl_registry=Registry(set(nl or []))
    )


def test_negative_sponsorship_wording_precedes_positive(config, job_factory):
    job = job_factory(
        country_code="gb",
        description="We mention visa sponsorship available, but no sponsorship is offered.",
    )
    result = engine(config, uk={"Example Technology"}).enrich(job)
    assert result.vacancy_authorisation_signal == "explicit_negative"
    assert result.work_authorisation_result == "unlikely"


def test_uk_register_is_employer_evidence_not_confirmation(config, job_factory):
    job = job_factory(country_code="gb", description="Build software in London.")
    result = engine(config, uk={"Example Technology Ltd"}).enrich(job)
    assert result.employer_authorisation == "recognised_or_licensed"
    assert result.work_authorisation_result == "possible"


def test_netherlands_register_evidence(config, job_factory):
    job = job_factory(country_code="nl", description="Highly Skilled Migrant visa support")
    result = engine(config, nl={"Example Technology BV"}).enrich(job)
    assert result.work_authorisation_result == "strong"
    assert result.permit_route == "nl_highly_skilled_migrant"


def test_germany_is_not_register_based(config, job_factory):
    result = engine(config).enrich(job_factory(description="EU Blue Card and relocation support"))
    assert result.employer_authorisation == "not_register_based"
    assert result.permit_route == "de_eu_blue_card"
    assert result.work_authorisation_result == "possible"


def test_ireland_critical_skills_route(config, job_factory):
    job = job_factory(
        country_code="ie", title="Software Engineer",
        description="Critical Skills Employment Permit support is available.",
    )
    result = engine(config).enrich(job)
    assert result.permit_route == "ie_critical_skills"
    assert result.work_authorisation_result == "strong"


def test_german_title_alias(config, job_factory):
    job = engine(config).enrich(job_factory(title="Junior Softwareentwickler"))
    score_job(job, config)
    assert job.canonical_role == "software_engineer"
    assert job.match_score > 0


def test_backend_engineer_alias(config, job_factory):
    job = engine(config).enrich(job_factory(title="Backend Engineer (Node.js)"))
    score_job(job, config)
    assert job.canonical_role == "software_engineer"
    assert job.match_score >= config.data["search"]["minimum_match_score"]


def test_role_exclusions_come_from_config(config, job_factory):
    job = engine(config).enrich(job_factory(title="Senior Software Engineer"))
    score_job(job, config)
    assert job.match_score == 0


def test_higher_salary_is_not_rejected(config, job_factory):
    job = engine(config).enrich(job_factory(salary_min=100000, salary_max=140000))
    score_job(job, config)
    assert job.match_score >= config.data["search"]["minimum_match_score"]


def test_missing_salary_is_small_penalty(config, job_factory):
    job = engine(config).enrich(job_factory(
        salary_min=None, salary_max=None, annual_salary_min_local=None,
        annual_salary_max_local=None,
    ))
    score_job(job, config)
    assert 0 < job.match_score <= 100
    assert "Salary not listed" in job.match_reasons


def test_scoring_bounds(config, job_factory):
    job = engine(config).enrich(job_factory())
    score_job(job, config)
    assert 0 <= job.match_score <= 100
    assert 0 <= job.eligibility_score <= 100
    assert 0 <= job.overall_score <= 100


def test_node_word_boundary_avoids_unrelated_word(config, job_factory):
    job = engine(config).enrich(job_factory(description="Work on inode allocation and React"))
    score_job(job, config)
    assert not any("Node.js" in reason for reason in job.match_reasons)


def test_dutch_html_registry_loader(config, monkeypatch):
    class Response:
        text = "<table><tr><th>Organisation</th></tr><tr><td>Example B.V.</td><td>123</td></tr></table>"
        content = text.encode()

        def raise_for_status(self):
            return None

    monkeypatch.setattr("src.eligibility.netherlands.requests.get", lambda *args, **kwargs: Response())
    assert download_nl_register(config) == {"Example B.V."}
