# tests/test_lever_scraper.py
"""Tests for the Lever job board scraper."""

from src.extract.lever_scraper import LeverScraper


SAMPLE_API_JOB = {
    "id": "d33ef090-2e71-43a2-ac10-cb81dfb13489",
    "text": "Senior Software Engineer",
    "categories": {
        "commitment": "Permanent",
        "department": "Engineering",
        "location": "San Francisco, CA (Remote)",
        "team": "Platform",
        "allLocations": ["San Francisco, CA"],
    },
    "descriptionPlain": "Build scalable distributed systems.",
    "description": "<div>Build scalable distributed systems.</div>",
    "additionalPlain": "The United States base range for this position is $180,000 - $250,000 plus equity.",
    "hostedUrl": "https://jobs.lever.co/spotify/d33ef090-2e71-43a2-ac10-cb81dfb13489",
    "applyUrl": "https://jobs.lever.co/spotify/d33ef090-2e71-43a2-ac10-cb81dfb13489/apply",
    "workplaceType": "remote",
    "country": "US",
    "createdAt": 1768231223728,
}


class TestLeverScraper:
    def test_normalize_sets_source(self):
        scraper = LeverScraper()
        job = scraper._normalize(SAMPLE_API_JOB, "spotify", "")
        assert job["source"] == "lever"

    def test_normalize_generates_job_id(self):
        scraper = LeverScraper()
        job = scraper._normalize(SAMPLE_API_JOB, "spotify", "")
        assert job["job_id"].startswith("lv_")

    def test_normalize_extracts_company_name(self):
        scraper = LeverScraper()
        job = scraper._normalize(SAMPLE_API_JOB, "spotify", "")
        assert job["company"] == "Spotify"

    def test_normalize_hyphenated_company_name(self):
        scraper = LeverScraper()
        job = scraper._normalize(SAMPLE_API_JOB, "dbt-labs", "")
        assert job["company"] == "Dbt Labs"

    def test_normalize_detects_remote_from_workplace_type(self):
        scraper = LeverScraper()
        job = scraper._normalize(SAMPLE_API_JOB, "spotify", "")
        assert job["remote"] is True

    def test_normalize_detects_remote_from_location(self):
        job_data = {**SAMPLE_API_JOB, "workplaceType": "onsite"}
        scraper = LeverScraper()
        job = scraper._normalize(job_data, "spotify", "")
        assert job["remote"] is True  # location contains "Remote"

    def test_normalize_not_remote(self):
        job_data = {
            **SAMPLE_API_JOB,
            "workplaceType": "onsite",
            "categories": {**SAMPLE_API_JOB["categories"], "location": "San Francisco, CA"},
        }
        scraper = LeverScraper()
        job = scraper._normalize(job_data, "spotify", "")
        assert job["remote"] is False

    def test_normalize_parses_salary(self):
        scraper = LeverScraper()
        job = scraper._normalize(SAMPLE_API_JOB, "spotify", "")
        assert job["salary_min"] == 180000
        assert job["salary_max"] == 250000
        assert job["currency"] == "USD"

    def test_normalize_no_salary(self):
        job_data = {**SAMPLE_API_JOB, "additionalPlain": "We offer great benefits."}
        scraper = LeverScraper()
        job = scraper._normalize(job_data, "spotify", "")
        assert job["salary_min"] is None
        assert job["salary_max"] is None
        assert job["currency"] is None

    def test_normalize_uses_plain_description(self):
        scraper = LeverScraper()
        job = scraper._normalize(SAMPLE_API_JOB, "spotify", "")
        assert "<div>" not in job["description"]
        assert "distributed systems" in job["description"]

    def test_normalize_extracts_location(self):
        scraper = LeverScraper()
        job = scraper._normalize(SAMPLE_API_JOB, "spotify", "")
        assert job["location"] == "San Francisco, CA (Remote)"

    def test_normalize_extracts_url(self):
        scraper = LeverScraper()
        job = scraper._normalize(SAMPLE_API_JOB, "spotify", "")
        assert "jobs.lever.co" in job["url"]

    def test_normalize_department_exposed_for_filtering(self):
        scraper = LeverScraper()
        job = scraper._normalize(SAMPLE_API_JOB, "spotify", "")
        assert job["_department"] == "Engineering"

    def test_parse_salary_range(self):
        salary_min, salary_max = LeverScraper._parse_salary(
            "The base range is $126,163 - $157,504 plus equity."
        )
        assert salary_min == 126163
        assert salary_max == 157504

    def test_parse_salary_none(self):
        salary_min, salary_max = LeverScraper._parse_salary("")
        assert salary_min is None
        assert salary_max is None

    def test_parse_salary_single_value(self):
        salary_min, salary_max = LeverScraper._parse_salary(
            "Base salary: $150,000 plus equity."
        )
        assert salary_min == 150000
        assert salary_max == 150000
