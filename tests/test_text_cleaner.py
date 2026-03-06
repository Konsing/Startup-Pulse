# tests/test_text_cleaner.py
"""Tests for the job description text cleaner."""

from src.transform.text_cleaner import TextCleaner


class TestTextCleaner:
    def test_clean_removes_html_tags(self):
        cleaner = TextCleaner()
        result = cleaner.clean_text("<p>Build <strong>APIs</strong> with Python</p>")
        assert "<p>" not in result
        assert "<strong>" not in result

    def test_clean_removes_urls(self):
        cleaner = TextCleaner()
        result = cleaner.clean_text("Apply at https://example.com/jobs")
        assert "https" not in result
        assert "example.com" not in result

    def test_clean_preserves_tech_terms(self):
        cleaner = TextCleaner()
        result = cleaner.clean_text("Experience with Python, React, and AWS required")
        assert "python" in result
        assert "react" in result
        assert "aws" in result

    def test_clean_empty_string(self):
        cleaner = TextCleaner()
        assert cleaner.clean_text("") == ""

    def test_clean_jobs_processes_all_records(self):
        cleaner = TextCleaner()
        jobs = [
            {"description": "Build APIs with Python", "title": "Backend Engineer"},
            {"description": "Design UIs with React", "title": "Frontend Dev"},
        ]
        result = cleaner.clean_jobs(jobs)
        assert len(result) == 2
        assert "cleaned_description" in result[0]
