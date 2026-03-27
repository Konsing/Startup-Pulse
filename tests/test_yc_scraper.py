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
        assert YCScraper._fetch_salary_from_page(None, "") == ""

    def test_map_salary_populates_lookup(self):
        lookup = {}
        YCScraper._map_salary(
            {"salary_min": 150000, "salary_max": 200000, "url": "/jobs/123"},
            lookup,
        )
        assert lookup["/jobs/123"] == "$150000 - $200000"
        assert lookup["https://www.workatastartup.com/jobs/123"] == "$150000 - $200000"

    def test_map_salary_skips_when_no_salary(self):
        lookup = {}
        YCScraper._map_salary({"url": "/jobs/123"}, lookup)
        assert len(lookup) == 0

    def test_collect_salary_from_company_hit(self):
        lookup = {}
        hit = {
            "name": "Acme Corp",
            "jobs": [
                {"salary_min": 120000, "salary_max": 180000, "url": "/jobs/1"},
                {"url": "/jobs/2"},  # no salary
            ],
        }
        YCScraper._collect_salary_from_hit(hit, lookup)
        assert lookup["/jobs/1"] == "$120000 - $180000"
        assert "/jobs/2" not in lookup
