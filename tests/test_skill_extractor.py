# tests/test_skill_extractor.py
"""Tests for the skill extractor."""

from src.transform.skill_extractor import SkillExtractor


SAMPLE_JOBS = [
    {
        "cleaned_description": "python fastapi postgresql aws docker kubernetes",
        "title": "Backend Engineer",
        "salary_min": 150000,
        "salary_max": 200000,
    },
    {
        "cleaned_description": "react typescript next.js tailwind frontend",
        "title": "Frontend Engineer",
        "salary_min": 130000,
        "salary_max": 170000,
    },
    {
        "cleaned_description": "python pytorch tensorflow machine learning deep learning",
        "title": "ML Engineer",
        "salary_min": 180000,
        "salary_max": 250000,
    },
]


class TestSkillExtractor:
    def test_taxonomy_match_finds_python(self):
        extractor = SkillExtractor()
        skills = extractor._taxonomy_match("experience with python and react required")
        assert "python" in skills
        assert "react" in skills

    def test_extract_returns_skill_records(self):
        extractor = SkillExtractor()
        results = extractor.extract(SAMPLE_JOBS)
        assert len(results) > 0
        assert "skill" in results[0]
        assert "frequency" in results[0]
        assert "category" in results[0]

    def test_extract_computes_avg_salary(self):
        extractor = SkillExtractor()
        results = extractor.extract(SAMPLE_JOBS)
        python_results = [r for r in results if r["skill"] == "python"]
        assert len(python_results) > 0
        assert python_results[0]["avg_salary"] is not None
        assert python_results[0]["avg_salary"] > 0
