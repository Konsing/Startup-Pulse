# tests/test_metrics_aggregator.py
"""Tests for the job market metrics aggregator."""

from src.transform.metrics_aggregator import MetricsAggregator


SAMPLE_JOBS = [
    {"source": "yc_wats", "title": "Backend Engineer", "salary_min": 150000, "salary_max": 200000,
     "remote": True, "company_stage": "Series A", "cleaned_description": "python aws"},
    {"source": "yc_wats", "title": "Frontend Engineer", "salary_min": 130000, "salary_max": 170000,
     "remote": False, "company_stage": "Series A", "cleaned_description": "react typescript"},
    {"source": "wellfound", "title": "ML Engineer", "salary_min": 180000, "salary_max": 250000,
     "remote": True, "company_stage": "Seed", "cleaned_description": "pytorch python"},
]


class TestMetricsAggregator:
    def test_aggregate_groups_by_source(self):
        agg = MetricsAggregator()
        results = agg.aggregate(SAMPLE_JOBS)
        sources = {r["source"] for r in results}
        assert "yc_wats" in sources
        assert "wellfound" in sources

    def test_aggregate_computes_remote_pct(self):
        agg = MetricsAggregator()
        results = agg.aggregate(SAMPLE_JOBS)
        yc = [r for r in results if r["source"] == "yc_wats"][0]
        assert yc["remote_pct"] == 50.0  # 1 of 2 is remote

    def test_aggregate_computes_avg_salary(self):
        agg = MetricsAggregator()
        results = agg.aggregate(SAMPLE_JOBS)
        wf = [r for r in results if r["source"] == "wellfound"][0]
        assert wf["avg_salary"] == 215000.0  # (180000+250000)/2
