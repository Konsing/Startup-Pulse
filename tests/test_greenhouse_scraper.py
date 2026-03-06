# tests/test_greenhouse_scraper.py
"""Tests for the Greenhouse job board scraper."""

from src.extract.greenhouse_scraper import GreenhouseScraper


SAMPLE_API_JOB = {
    "id": 12345,
    "title": "Senior Backend Engineer",
    "company_name": "Stripe",
    "location": {"name": "San Francisco, CA (Remote)"},
    "content": "<p>Build <b>payment</b> infrastructure.</p>",
    "absolute_url": "https://boards.greenhouse.io/stripe/jobs/12345",
    "departments": [{"id": 1, "name": "Engineering"}],
    "offices": [{"id": 1, "name": "US"}],
    "metadata": [
        {"id": 1, "name": "Salary Range", "value": "$180,000 - $250,000"},
    ],
    "updated_at": "2026-03-01T10:00:00-05:00",
}


class TestGreenhouseScraper:
    def test_normalize_sets_source(self):
        scraper = GreenhouseScraper()
        job = scraper._normalize(SAMPLE_API_JOB, "stripe")
        assert job["source"] == "greenhouse"

    def test_normalize_generates_job_id(self):
        scraper = GreenhouseScraper()
        job = scraper._normalize(SAMPLE_API_JOB, "stripe")
        assert job["job_id"].startswith("gh_")

    def test_normalize_extracts_company_name(self):
        scraper = GreenhouseScraper()
        job = scraper._normalize(SAMPLE_API_JOB, "stripe")
        assert job["company"] == "Stripe"

    def test_normalize_detects_remote(self):
        scraper = GreenhouseScraper()
        job = scraper._normalize(SAMPLE_API_JOB, "stripe")
        assert job["remote"] is True

    def test_normalize_strips_html(self):
        scraper = GreenhouseScraper()
        job = scraper._normalize(SAMPLE_API_JOB, "stripe")
        assert "<p>" not in job["description"]
        assert "payment" in job["description"]

    def test_normalize_parses_salary_from_metadata(self):
        scraper = GreenhouseScraper()
        job = scraper._normalize(SAMPLE_API_JOB, "stripe")
        assert job["salary_min"] == 180000
        assert job["salary_max"] == 250000

    def test_normalize_no_salary_metadata(self):
        job_data = {**SAMPLE_API_JOB, "metadata": None}
        scraper = GreenhouseScraper()
        job = scraper._normalize(job_data, "stripe")
        assert job["salary_min"] is None
        assert job["salary_max"] is None

    def test_normalize_falls_back_to_board_token(self):
        job_data = {**SAMPLE_API_JOB, "company_name": None}
        scraper = GreenhouseScraper()
        job = scraper._normalize(job_data, "stripe")
        assert job["company"] == "stripe"
