# tests/test_yc_scraper.py
"""Tests for the YC Work at a Startup scraper."""

from src.extract.yc_scraper import YCScraper


SAMPLE_RAW_JOB = {
    "title": "Senior Software Engineer",
    "company": "Acme AI",
    "location": "San Francisco, CA",
    "salary": "$150K - $200K",
    "description": "Build ML pipelines using Python and PyTorch.",
    "url": "https://www.workatastartup.com/jobs/12345",
    "batch": "S24",
}


class TestYCScraper:
    def test_normalize_job_sets_source(self):
        scraper = YCScraper()
        job = scraper._normalize(SAMPLE_RAW_JOB)
        assert job["source"] == "yc_wats"

    def test_normalize_job_generates_job_id(self):
        scraper = YCScraper()
        job = scraper._normalize(SAMPLE_RAW_JOB)
        assert job["job_id"].startswith("yc_")

    def test_normalize_job_preserves_batch(self):
        scraper = YCScraper()
        job = scraper._normalize(SAMPLE_RAW_JOB)
        assert job["yc_batch"] == "S24"

    def test_normalize_job_parses_salary_range(self):
        scraper = YCScraper()
        job = scraper._normalize(SAMPLE_RAW_JOB)
        assert job["salary_min"] == 150000
        assert job["salary_max"] == 200000

    def test_normalize_job_no_salary(self):
        raw = {**SAMPLE_RAW_JOB, "salary": ""}
        scraper = YCScraper()
        job = scraper._normalize(raw)
        assert job["salary_min"] is None
        assert job["salary_max"] is None

    def test_parse_salary_json_ld_format(self):
        assert YCScraper._parse_salary("$150000 - $200000") == (150000, 200000)

    def test_parse_salary_k_format(self):
        assert YCScraper._parse_salary("$150K - $200K") == (150000, 200000)

    def test_fetch_salary_from_page_empty_url(self):
        assert YCScraper._fetch_salary_from_page("") == ""
