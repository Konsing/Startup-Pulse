"""BigQuery loader for the Startup Pulse pipeline.

Loads cleaned jobs, skill trends, and market metrics into BigQuery
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

from src.utils.deduplication import deduplicate_in_run, get_existing_job_ids

logger = logging.getLogger(__name__)

_MAX_RETRIES = 3
_BACKOFF_BASE = 2  # seconds; exponential: 2, 4, 8


class BigQueryLoader:
    """Loads transformed data into BigQuery tables."""

    def __init__(self) -> None:
        self.project_id = os.environ["GCP_PROJECT_ID"]
        self.dataset = os.environ.get("BQ_DATASET", "startup_pulse")
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
        skills_path: str,
        metrics_path: str,
    ) -> dict:
        """Orchestrate loading of all three datasets.

        Args:
            cleaned_path: Path to cleaned ``jobs.json``.
            skills_path: Path to ``skills.json``.
            metrics_path: Path to ``metrics.json``.

        Returns:
            Dict with counts: ``jobs_loaded``, ``skills_loaded``,
            ``metrics_loaded``.
        """
        logger.info("Starting BigQuery load from %s, %s, %s", cleaned_path, skills_path, metrics_path)

        with open(cleaned_path, "r", encoding="utf-8") as fh:
            jobs_data = json.load(fh)

        with open(skills_path, "r", encoding="utf-8") as fh:
            skills_data = json.load(fh)

        with open(metrics_path, "r", encoding="utf-8") as fh:
            metrics_data = json.load(fh)

        jobs_loaded = self.load_jobs(jobs_data)
        skills_loaded = self.load_skills(skills_data)
        metrics_loaded = self.load_metrics(metrics_data)

        result = {
            "jobs_loaded": jobs_loaded,
            "skills_loaded": skills_loaded,
            "metrics_loaded": metrics_loaded,
        }
        logger.info("BigQuery load complete: %s", result)
        return result

    def load_jobs(self, jobs_data: list[dict]) -> int:
        """Load job records into the ``raw_jobs`` table.

        Performs in-run deduplication, cross-run deduplication against
        BigQuery, validates rows, and appends to the table.

        Returns:
            Number of rows loaded.
        """
        if not jobs_data:
            logger.warning("No jobs to load.")
            return 0

        table_id = f"{self.project_id}.{self.dataset}.raw_jobs"

        # In-run deduplication
        jobs_data = deduplicate_in_run(jobs_data)

        # Cross-run deduplication
        existing_ids = get_existing_job_ids(self.client, table_id)
        if existing_ids:
            before = len(jobs_data)
            jobs_data = [j for j in jobs_data if j["job_id"] not in existing_ids]
            logger.info(
                "Cross-run dedup: filtered %d -> %d jobs.", before, len(jobs_data)
            )

        if not jobs_data:
            logger.info("All jobs already loaded; nothing to insert.")
            return 0

        df = pd.DataFrame(jobs_data)

        # Validate: drop rows with null job_id
        null_ids = df["job_id"].isna().sum()
        if null_ids:
            logger.warning("Dropping %d rows with null job_id.", null_ids)
            df = df.dropna(subset=["job_id"])

        # Truncate description to 10K chars
        if "description" in df.columns:
            df["description"] = df["description"].astype(str).str[:10000]

        # Convert timestamp columns
        if "collected_at" in df.columns:
            df["collected_at"] = pd.to_datetime(df["collected_at"], utc=True)

        row_count = len(df)
        self._load_dataframe(df, table_id)
        logger.info("Loaded %d jobs to %s.", row_count, table_id)
        return row_count

    def load_skills(self, skills_data: list[dict]) -> int:
        """Load skill trend records into the ``skill_trends`` table.

        Returns:
            Number of rows loaded.
        """
        if not skills_data:
            logger.warning("No skills to load.")
            return 0

        table_id = f"{self.project_id}.{self.dataset}.skill_trends"

        # Add collected_at timestamp
        now = datetime.now(timezone.utc).isoformat()
        for record in skills_data:
            record["collected_at"] = now

        df = pd.DataFrame(skills_data)
        df["collected_at"] = pd.to_datetime(df["collected_at"], utc=True)

        row_count = len(df)
        self._load_dataframe(df, table_id)
        logger.info("Loaded %d skill records to %s.", row_count, table_id)
        return row_count

    def load_metrics(self, metrics_data: list[dict]) -> int:
        """Load market metric records into the ``market_metrics`` table.

        Returns:
            Number of rows loaded.
        """
        if not metrics_data:
            logger.warning("No metrics to load.")
            return 0

        table_id = f"{self.project_id}.{self.dataset}.market_metrics"

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
        """Attempt to create a missing table by running the init script logic."""
        from scripts.init_bigquery import main as init_main

        logger.info("Running BigQuery table initialization for %s...", table_id)
        try:
            init_main()
            logger.info("Table initialization completed.")
        except Exception as exc:
            logger.error("Failed to initialize tables: %s", exc)
            raise
