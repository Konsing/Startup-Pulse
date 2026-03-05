"""Metrics aggregation per subreddit/category group.

Groups cleaned posts by (subreddit, category) and computes summary
statistics including scores, comments, upvote ratios, and posting rates.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)


class MetricsAggregator:
    """Aggregate engagement metrics per subreddit/category."""

    def aggregate(self, input_path: str, output_path: str) -> dict:
        """Read cleaned posts, compute aggregated metrics, and write results.

        Args:
            input_path: Path to the cleaned ``posts.json`` file.
            output_path: Path where ``metrics.json`` will be written.

        Returns:
            Metadata dict with ``subreddits_aggregated``.
        """
        logger.info("Reading cleaned posts from %s", input_path)
        with open(input_path, "r", encoding="utf-8") as fh:
            posts = json.load(fh)

        df = pd.DataFrame(posts)
        all_metrics: list[dict] = []

        for (subreddit, category), group_df in df.groupby(["subreddit", "category"]):
            # Parse created_utc timestamps for posting-rate calculation
            timestamps = pd.to_datetime(group_df["created_utc"], utc=True)
            time_spread_hours = 0.0
            if len(timestamps) > 1:
                time_spread = (timestamps.max() - timestamps.min()).total_seconds() / 3600
                time_spread_hours = time_spread if time_spread > 0 else 0.0

            posting_rate = (
                len(group_df) / time_spread_hours
                if time_spread_hours > 0
                else 0.0
            )

            metrics = {
                "subreddit": subreddit,
                "category": category,
                "total_posts_collected": int(len(group_df)),
                "avg_score": float(group_df["score"].mean()),
                "median_score": float(group_df["score"].median()),
                "max_score": int(group_df["score"].max()),
                "avg_comments": float(group_df["num_comments"].mean()),
                "total_comments": int(group_df["num_comments"].sum()),
                "avg_upvote_ratio": float(group_df["upvote_ratio"].mean()),
                "posting_rate_per_hour": float(posting_rate),
                "collected_at": datetime.now(timezone.utc).isoformat(),
            }
            all_metrics.append(metrics)

        # Write results
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as fh:
            json.dump(all_metrics, fh, ensure_ascii=False, indent=2)

        metadata = {
            "subreddits_aggregated": len(all_metrics),
        }
        logger.info(
            "Aggregated metrics for %d subreddits -> %s",
            metadata["subreddits_aggregated"],
            output_path,
        )
        return metadata
