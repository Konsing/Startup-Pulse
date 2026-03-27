#!/usr/bin/env python3
"""Standalone pipeline runner (no Airflow required).

Runs the full ETL pipeline: scrape -> clean -> skills + metrics -> load.
Used by GitHub Actions and for local development without Docker.
"""

import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Ensure project root is on sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("pipeline")

DATA_DIR = os.environ.get("PIPELINE_DATA_DIR", "pipeline_data")


def run_scrapers(execution_date: str) -> None:
    """Run all 4 scrapers, saving results to DATA_DIR/raw/{source}/{date}/."""
    from src.extract.yc_scraper import YCScraper
    from src.extract.greenhouse_scraper import GreenhouseScraper
    from src.extract.ashby_scraper import AshbyScraper
    from src.extract.hn_scraper import HNScraper
    from src.extract.lever_scraper import LeverScraper

    scrapers = [
        ("yc", YCScraper()),
        ("greenhouse", GreenhouseScraper()),
        ("ashby", AshbyScraper()),
        ("hn", HNScraper()),
        ("lever", LeverScraper()),
    ]

    for name, scraper in scrapers:
        output_dir = f"{DATA_DIR}/raw/{name}/{execution_date}"
        try:
            result = scraper.scrape(output_dir)
            logger.info("Scraper [%s]: %s", name, result)
        except Exception as exc:
            logger.error("Scraper [%s] failed: %s", name, exc)


def run_clean(execution_date: str) -> None:
    """Merge all scraped jobs and clean text fields."""
    from src.transform.text_cleaner import TextCleaner

    all_jobs = []
    for source in ("yc", "greenhouse", "ashby", "hn", "lever"):
        path = f"{DATA_DIR}/raw/{source}/{execution_date}/jobs.json"
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as fh:
                jobs = json.load(fh)
                all_jobs.extend(jobs)
                logger.info("Loaded %d jobs from %s", len(jobs), source)

    cleaner = TextCleaner()
    cleaned = cleaner.clean_jobs(all_jobs)

    output_dir = f"{DATA_DIR}/cleaned/{execution_date}"
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    with open(f"{output_dir}/jobs.json", "w", encoding="utf-8") as fh:
        json.dump(cleaned, fh, ensure_ascii=False, indent=2)

    logger.info("Cleaned %d total jobs", len(cleaned))


def run_skills(execution_date: str) -> None:
    """Extract skill trends from cleaned jobs."""
    from src.transform.skill_extractor import SkillExtractor

    with open(f"{DATA_DIR}/cleaned/{execution_date}/jobs.json", "r") as fh:
        jobs = json.load(fh)

    results = SkillExtractor().extract(jobs)

    output_dir = f"{DATA_DIR}/skills/{execution_date}"
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    with open(f"{output_dir}/skills.json", "w", encoding="utf-8") as fh:
        json.dump(results, fh, ensure_ascii=False, indent=2)

    logger.info("Extracted %d skills", len(results))


def run_metrics(execution_date: str) -> None:
    """Aggregate market metrics from cleaned jobs."""
    from src.transform.metrics_aggregator import MetricsAggregator

    with open(f"{DATA_DIR}/cleaned/{execution_date}/jobs.json", "r") as fh:
        jobs = json.load(fh)

    results = MetricsAggregator().aggregate(jobs)

    output_dir = f"{DATA_DIR}/metrics/{execution_date}"
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    with open(f"{output_dir}/metrics.json", "w", encoding="utf-8") as fh:
        json.dump(results, fh, ensure_ascii=False, indent=2)

    logger.info("Aggregated metrics for %d sources", len(results))


def run_load(execution_date: str) -> None:
    """Load all data into BigQuery."""
    from src.load.bigquery_loader import BigQueryLoader

    loader = BigQueryLoader()
    result = loader.load_all(
        cleaned_path=f"{DATA_DIR}/cleaned/{execution_date}/jobs.json",
        skills_path=f"{DATA_DIR}/skills/{execution_date}/skills.json",
        metrics_path=f"{DATA_DIR}/metrics/{execution_date}/metrics.json",
    )
    logger.info("BigQuery load result: %s", result)


def main() -> None:
    execution_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    logger.info("=== Pipeline start (date=%s) ===", execution_date)

    run_scrapers(execution_date)
    run_clean(execution_date)
    run_skills(execution_date)
    run_metrics(execution_date)
    run_load(execution_date)

    logger.info("=== Pipeline complete ===")


if __name__ == "__main__":
    main()
