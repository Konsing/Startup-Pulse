"""BigQuery loader for the Reddit Trends pipeline.

Loads cleaned posts, keyword trends, and subreddit metrics into BigQuery
with deduplication, validation, and retry logic.
"""

import json
import logging
import os
import time
from datetime import datetime, timezone

import pandas as pd
from google.api_core.exceptions import NotFound, ServiceUnavailable
from google.cloud import bigquery

from src.utils.deduplication import deduplicate_in_run, get_existing_post_ids

logger = logging.getLogger(__name__)

_MAX_RETRIES = 3
_BACKOFF_BASE = 2  # seconds; exponential: 2, 4, 8


class BigQueryLoader:
    """Loads transformed data into BigQuery tables."""

    def __init__(self) -> None:
        self.project_id = os.environ["GCP_PROJECT_ID"]
        self.dataset = os.environ.get("BQ_DATASET", "reddit_trends")
        self.client = bigquery.Client(project=self.project_id)
        logger.info(
            "BigQueryLoader initialized (project=%s, dataset=%s).",
            self.project_id,
            self.dataset,
        )

    # ── Public API ────────────────────────────────────────────────────

    def load_all(
        self,
        cleaned_path: str,
        keywords_path: str,
        metrics_path: str,
    ) -> dict:
        """Orchestrate loading of all three datasets.

        Args:
            cleaned_path: Path to cleaned ``posts.json``.
            keywords_path: Path to ``keywords.json``.
            metrics_path: Path to ``metrics.json``.

        Returns:
            Dict with counts: ``posts_loaded``, ``keywords_loaded``,
            ``metrics_loaded``.
        """
        logger.info("Starting BigQuery load from %s, %s, %s", cleaned_path, keywords_path, metrics_path)

        with open(cleaned_path, "r", encoding="utf-8") as fh:
            posts_data = json.load(fh)

        with open(keywords_path, "r", encoding="utf-8") as fh:
            keywords_data = json.load(fh)

        with open(metrics_path, "r", encoding="utf-8") as fh:
            metrics_data = json.load(fh)

        posts_loaded = self.load_posts(posts_data)
        keywords_loaded = self.load_keywords(keywords_data)
        metrics_loaded = self.load_metrics(metrics_data)

        result = {
            "posts_loaded": posts_loaded,
            "keywords_loaded": keywords_loaded,
            "metrics_loaded": metrics_loaded,
        }
        logger.info("BigQuery load complete: %s", result)
        return result

    def load_posts(self, posts_data: list[dict]) -> int:
        """Load post records into the ``raw_posts`` table.

        Performs in-run deduplication, cross-run deduplication against
        BigQuery, validates rows, and appends to the table.

        Returns:
            Number of rows loaded.
        """
        if not posts_data:
            logger.warning("No posts to load.")
            return 0

        table_id = f"{self.project_id}.{self.dataset}.raw_posts"

        # In-run deduplication
        posts_data = deduplicate_in_run(posts_data)

        # Cross-run deduplication
        existing_ids = get_existing_post_ids(self.client, table_id)
        if existing_ids:
            before = len(posts_data)
            posts_data = [p for p in posts_data if p["post_id"] not in existing_ids]
            logger.info(
                "Cross-run dedup: filtered %d -> %d posts.", before, len(posts_data)
            )

        if not posts_data:
            logger.info("All posts already loaded; nothing to insert.")
            return 0

        df = pd.DataFrame(posts_data)

        # Validate: drop rows with null post_id
        null_ids = df["post_id"].isna().sum()
        if null_ids:
            logger.warning("Dropping %d rows with null post_id.", null_ids)
            df = df.dropna(subset=["post_id"])

        # Truncate selftext to 10K chars
        if "selftext" in df.columns:
            df["selftext"] = df["selftext"].astype(str).str[:10000]

        # Convert timestamp columns
        for ts_col in ("created_utc", "collected_at"):
            if ts_col in df.columns:
                df[ts_col] = pd.to_datetime(df[ts_col], utc=True)

        # Ensure correct integer dtypes
        for int_col in ("score", "num_comments"):
            if int_col in df.columns:
                df[int_col] = df[int_col].astype(int)

        row_count = len(df)
        self._load_dataframe(df, table_id)
        logger.info("Loaded %d posts to %s.", row_count, table_id)
        return row_count

    def load_keywords(self, keywords_data: list[dict]) -> int:
        """Load keyword trend records into the ``keyword_trends`` table.

        Returns:
            Number of rows loaded.
        """
        if not keywords_data:
            logger.warning("No keywords to load.")
            return 0

        table_id = f"{self.project_id}.{self.dataset}.keyword_trends"

        # Add collected_at timestamp
        now = datetime.now(timezone.utc).isoformat()
        for record in keywords_data:
            record["collected_at"] = now

        df = pd.DataFrame(keywords_data)
        df["collected_at"] = pd.to_datetime(df["collected_at"], utc=True)

        row_count = len(df)
        self._load_dataframe(df, table_id)
        logger.info("Loaded %d keyword records to %s.", row_count, table_id)
        return row_count

    def load_metrics(self, metrics_data: list[dict]) -> int:
        """Load subreddit metric records into the ``subreddit_metrics`` table.

        Returns:
            Number of rows loaded.
        """
        if not metrics_data:
            logger.warning("No metrics to load.")
            return 0

        table_id = f"{self.project_id}.{self.dataset}.subreddit_metrics"

        df = pd.DataFrame(metrics_data)
        df["collected_at"] = pd.to_datetime(df["collected_at"], utc=True)

        row_count = len(df)
        self._load_dataframe(df, table_id)
        logger.info("Loaded %d metric records to %s.", row_count, table_id)
        return row_count

    # ── Private helpers ───────────────────────────────────────────────

    def _load_dataframe(self, df: pd.DataFrame, table_id: str) -> None:
        """Load a DataFrame into BigQuery with retry and auto-create logic.

        Retries up to ``_MAX_RETRIES`` times on ``ServiceUnavailable``.
        On ``NotFound``, attempts to create the table from the init script,
        then retries the load.
        """
        job_config = bigquery.LoadJobConfig(write_disposition="WRITE_APPEND")

        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                job = self.client.load_table_from_dataframe(
                    df, table_id, job_config=job_config
                )
                job.result()  # wait for completion
                return
            except NotFound:
                logger.warning(
                    "Table %s not found (attempt %d/%d). Creating table...",
                    table_id,
                    attempt,
                    _MAX_RETRIES,
                )
                self._create_table_from_init(table_id)
                # Retry on next iteration
            except ServiceUnavailable as exc:
                if attempt < _MAX_RETRIES:
                    wait = _BACKOFF_BASE ** attempt
                    logger.warning(
                        "ServiceUnavailable on attempt %d/%d for %s. "
                        "Retrying in %ds: %s",
                        attempt,
                        _MAX_RETRIES,
                        table_id,
                        wait,
                        exc,
                    )
                    time.sleep(wait)
                else:
                    logger.error(
                        "Failed to load to %s after %d attempts.", table_id, _MAX_RETRIES
                    )
                    raise

    def _create_table_from_init(self, table_id: str) -> None:
        """Attempt to create a missing table by running the init script logic.

        This is a fallback for when tables haven't been created yet.
        """
        from scripts.init_bigquery import main as init_main

        logger.info("Running BigQuery table initialization for %s...", table_id)
        try:
            init_main()
            logger.info("Table initialization completed.")
        except Exception as exc:
            logger.error("Failed to initialize tables: %s", exc)
            raise
