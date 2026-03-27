# tests/test_hn_scraper.py
"""Tests for the Hacker News 'Who is Hiring?' scraper."""

import json
from unittest.mock import patch, MagicMock

import pytest

from src.extract.hn_scraper import HNScraper


SAMPLE_COMMENT = {
    "id": 99001,
    "by": "techstartup",
    "text": "Acme Corp | Senior Backend Engineer | San Francisco, CA | ONSITE, REMOTE | $180k-$220k<p>We&#x27;re building the future of payments. Stack: Python, FastAPI, PostgreSQL, AWS.<p>Apply: https://acme.example.com/jobs/123",
    "type": "comment",
    "parent": 99000,
    "time": 1709251200,
}


class TestHNScraper:
    def test_parse_hn_comment_extracts_company(self):
        scraper = HNScraper()
        job = scraper._parse_comment(SAMPLE_COMMENT)
        assert job["company"] == "Acme Corp"

    def test_parse_hn_comment_extracts_title(self):
        scraper = HNScraper()
        job = scraper._parse_comment(SAMPLE_COMMENT)
        assert job["title"] == "Senior Backend Engineer"

    def test_parse_hn_comment_extracts_location(self):
        scraper = HNScraper()
        job = scraper._parse_comment(SAMPLE_COMMENT)
        assert "San Francisco" in job["location"]

    def test_parse_hn_comment_detects_remote(self):
        scraper = HNScraper()
        job = scraper._parse_comment(SAMPLE_COMMENT)
        assert job["remote"] is True

    def test_parse_hn_comment_sets_source(self):
        scraper = HNScraper()
        job = scraper._parse_comment(SAMPLE_COMMENT)
        assert job["source"] == "hackernews"

    def test_parse_hn_comment_extracts_salary(self):
        scraper = HNScraper()
        job = scraper._parse_comment(SAMPLE_COMMENT)
        assert job["salary_min"] == 180000
        assert job["salary_max"] == 220000
        assert job["currency"] == "USD"

    def test_parse_hn_comment_no_salary(self):
        scraper = HNScraper()
        comment = {**SAMPLE_COMMENT, "text": "Acme Corp | Engineer | SF, CA | REMOTE<p>We build stuff."}
        job = scraper._parse_comment(comment)
        assert job["salary_min"] is None
        assert job["salary_max"] is None

    def test_parse_hn_comment_returns_none_for_non_job(self):
        scraper = HNScraper()
        non_job = {"id": 1, "text": "Is anyone else having trouble with the thread?", "type": "comment", "by": "user", "parent": 99000, "time": 1709251200}
        assert scraper._parse_comment(non_job) is None

    def test_extract_salary_range_k_format(self):
        assert HNScraper._extract_salary_range("$150k-$200k") == (150000, 200000)

    def test_extract_salary_range_full_format(self):
        assert HNScraper._extract_salary_range("$150,000 - $200,000") == (150000, 200000)

    def test_extract_salary_range_no_match(self):
        assert HNScraper._extract_salary_range("great pay") == (None, None)
