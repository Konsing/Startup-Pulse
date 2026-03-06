# src/transform/metrics_aggregator.py
"""Market metrics aggregation per source and role category.

Groups cleaned jobs by source, computes summary statistics
including salary ranges, remote percentages, and job counts.
"""

import json
import logging
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from src.utils.config import ROLE_CATEGORIES

logger = logging.getLogger(__name__)


class MetricsAggregator:
    """Aggregate job market metrics by source and role category."""

    def aggregate(self, jobs: list[dict]) -> list[dict]:
        """Compute market metrics from cleaned job dicts.

        Args:
            jobs: List of normalized job dicts.

        Returns:
            List of metric dicts grouped by source.
        """
        if not jobs:
            return []

        # Group by source
        by_source: dict[str, list[dict]] = defaultdict(list)
        for job in jobs:
            by_source[job.get("source", "unknown")].append(job)

        results = []
        now = datetime.now(timezone.utc).isoformat()

        for source, group in by_source.items():
            # Salary stats (only from jobs with salary data)
            salaries = [
                (j["salary_min"] + j["salary_max"]) / 2
                for j in group
                if j.get("salary_min") and j.get("salary_max")
            ]

            # Remote percentage
            remote_count = sum(1 for j in group if j.get("remote"))
            remote_pct = (remote_count / len(group) * 100) if group else 0.0

            # Top role category
            role_counts = self._classify_roles(group)
            top_skills_str = ", ".join(
                k for k, _ in sorted(role_counts.items(), key=lambda x: -x[1])[:5]
            )

            results.append({
                "source": source,
                "role_category": "all",
                "total_jobs": len(group),
                "avg_salary": float(np.mean(salaries)) if salaries else None,
                "median_salary": float(np.median(salaries)) if salaries else None,
                "remote_pct": round(remote_pct, 1),
                "top_skills": top_skills_str or None,
                "collected_at": now,
            })

        logger.info("Aggregated metrics for %d sources", len(results))
        return results

    @staticmethod
    def _classify_roles(jobs: list[dict]) -> dict[str, int]:
        """Count jobs per role category using keyword matching on titles."""
        counts: dict[str, int] = defaultdict(int)
        for job in jobs:
            title = (job.get("title", "") + " " + job.get("cleaned_description", "")).lower()
            for category, keywords in ROLE_CATEGORIES.items():
                if any(kw in title for kw in keywords):
                    counts[category] += 1
                    break
        return dict(counts)
