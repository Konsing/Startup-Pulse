# tests/test_wellfound_scraper.py
"""Tests for the Wellfound job scraper."""

from src.extract.wellfound_scraper import WellfoundScraper


SAMPLE_RAW_JOB = {
    "title": "ML Engineer",
    "company": "DataCo",
    "location": "Remote (US)",
    "salary": "$120k – $180k",
    "equity": "0.5% - 1.0%",
    "stage": "Series A",
    "description": "Build recommendation systems.",
    "url": "https://wellfound.com/l/dataco-ml-engineer",
}


class TestWellfoundScraper:
    def test_normalize_sets_source(self):
        scraper = WellfoundScraper()
        job = scraper._normalize(SAMPLE_RAW_JOB)
        assert job["source"] == "wellfound"

    def test_normalize_extracts_equity(self):
        scraper = WellfoundScraper()
        job = scraper._normalize(SAMPLE_RAW_JOB)
        assert job["equity"] == "0.5% - 1.0%"

    def test_normalize_extracts_company_stage(self):
        scraper = WellfoundScraper()
        job = scraper._normalize(SAMPLE_RAW_JOB)
        assert job["company_stage"] == "Series A"

    def test_normalize_detects_remote(self):
        scraper = WellfoundScraper()
        job = scraper._normalize(SAMPLE_RAW_JOB)
        assert job["remote"] is True

    def test_normalize_parses_salary(self):
        scraper = WellfoundScraper()
        job = scraper._normalize(SAMPLE_RAW_JOB)
        assert job["salary_min"] == 120000
        assert job["salary_max"] == 180000
