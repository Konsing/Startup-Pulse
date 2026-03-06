# tests/test_ashby_scraper.py
"""Tests for the Ashby ATS job board scraper."""

from src.extract.ashby_scraper import AshbyScraper


SAMPLE_API_JOB = {
    "id": "abc-123",
    "title": "Senior Backend Engineer",
    "department": None,
    "team": None,
    "employmentType": "FullTime",
    "location": "San Francisco, CA",
    "isRemote": True,
    "descriptionHtml": "<p>Build <b>distributed</b> systems.</p>",
    "descriptionPlain": "Build distributed systems.",
    "jobUrl": "https://jobs.ashbyhq.com/linear/abc-123",
    "applyUrl": "https://jobs.ashbyhq.com/linear/abc-123/application",
}


class TestAshbyScraper:
    def test_normalize_sets_source(self):
        scraper = AshbyScraper()
        job = scraper._normalize(SAMPLE_API_JOB, "linear")
        assert job["source"] == "ashby"

    def test_normalize_generates_job_id(self):
        scraper = AshbyScraper()
        job = scraper._normalize(SAMPLE_API_JOB, "linear")
        assert job["job_id"].startswith("ab_")

    def test_normalize_detects_remote(self):
        scraper = AshbyScraper()
        job = scraper._normalize(SAMPLE_API_JOB, "linear")
        assert job["remote"] is True

    def test_normalize_strips_html(self):
        scraper = AshbyScraper()
        job = scraper._normalize(SAMPLE_API_JOB, "linear")
        assert "<p>" not in job["description"]
        assert "distributed" in job["description"]

    def test_normalize_title_case_company(self):
        scraper = AshbyScraper()
        job = scraper._normalize(SAMPLE_API_JOB, "posthog")
        assert job["company"] == "Posthog"

    def test_normalize_appends_remote_to_location(self):
        scraper = AshbyScraper()
        job = scraper._normalize(SAMPLE_API_JOB, "linear")
        assert "Remote" in job["location"]
