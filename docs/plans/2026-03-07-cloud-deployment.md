# Cloud Deployment Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Deploy the Startup Pulse pipeline to free cloud services — GitHub Actions for ETL orchestration, Streamlit Community Cloud for the dashboard.

**Architecture:** GitHub Actions runs a cron workflow (daily + manual trigger) that installs deps, runs all 4 scrapers, transforms, and loads to BigQuery. Streamlit Community Cloud hosts the dashboard, reading from BigQuery via Streamlit secrets. Both paths support the existing local Docker Compose setup without conflicts.

**Tech Stack:** GitHub Actions, Streamlit Community Cloud, Google Cloud BigQuery, Python 3.11

---

### Task 1: Create Pipeline Runner Script

**Files:**
- Create: `scripts/run_pipeline.py`

This script replaces the Airflow DAG for non-Airflow environments. It runs the same ETL steps sequentially: scrape all 4 sources, clean, extract skills, aggregate metrics, load to BigQuery.

**Step 1: Create the runner script**

```python
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

    scrapers = [
        ("yc", YCScraper()),
        ("greenhouse", GreenhouseScraper()),
        ("ashby", AshbyScraper()),
        ("hn", HNScraper()),
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
    for source in ("yc", "greenhouse", "ashby", "hn"):
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
```

**Step 2: Verify syntax**

Run: `python3 -c "import py_compile; py_compile.compile('scripts/run_pipeline.py', doraise=True); print('OK')"`
Expected: `OK`

**Step 3: Commit**

```bash
git add scripts/run_pipeline.py
git commit -m "Add standalone pipeline runner for GitHub Actions"
```

---

### Task 2: Create GitHub Actions Workflow

**Files:**
- Create: `.github/workflows/pipeline.yml`

The workflow runs daily at 08:00 UTC and supports manual triggers via `workflow_dispatch`. It installs Python deps, Playwright browsers, sets up GCP credentials from a secret, and runs the pipeline.

**Step 1: Create the workflow file**

```yaml
name: ETL Pipeline

on:
  schedule:
    - cron: '0 8 * * *'
  workflow_dispatch:

jobs:
  run-pipeline:
    runs-on: ubuntu-latest
    timeout-minutes: 30

    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          pip install playwright requests beautifulsoup4 \
            'google-cloud-bigquery[pandas,pyarrow]' pandas nltk \
            scikit-learn db-dtypes
          playwright install --with-deps chromium

      - name: Set up GCP credentials
        run: echo '${{ secrets.GCP_SA_KEY }}' > /tmp/sa-key.json
        env:
          GCP_SA_KEY: ${{ secrets.GCP_SA_KEY }}

      - name: Run pipeline
        env:
          GOOGLE_APPLICATION_CREDENTIALS: /tmp/sa-key.json
          GCP_PROJECT_ID: ${{ secrets.GCP_PROJECT_ID }}
          BQ_DATASET: ${{ secrets.BQ_DATASET }}
        run: python scripts/run_pipeline.py

      - name: Cleanup credentials
        if: always()
        run: rm -f /tmp/sa-key.json
```

**Step 2: Commit**

```bash
mkdir -p .github/workflows
git add .github/workflows/pipeline.yml
git commit -m "Add GitHub Actions workflow for daily ETL pipeline"
```

---

### Task 3: Update Streamlit App for Cloud Deployment

**Files:**
- Modify: `streamlit_app/utils/bq_client.py`
- Create: `streamlit_app/.streamlit/config.toml`

Streamlit Community Cloud uses `st.secrets` for credentials instead of env vars / files. Update `bq_client.py` to support both: env var (local Docker) and Streamlit secrets (cloud).

**Step 1: Update bq_client.py**

```python
"""BigQuery client utilities for the Streamlit dashboard."""

import os

import pandas as pd
import streamlit as st
from google.cloud import bigquery
from google.oauth2 import service_account

_client = None


def get_client() -> bigquery.Client:
    """Return a cached BigQuery client.

    Supports two auth modes:
    - GOOGLE_APPLICATION_CREDENTIALS env var (local Docker / dev)
    - Streamlit secrets with [gcp_service_account] section (Streamlit Cloud)
    """
    global _client
    if _client is not None:
        return _client

    project = os.environ.get("GCP_PROJECT_ID") or st.secrets.get("GCP_PROJECT_ID")

    if os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
        _client = bigquery.Client(project=project)
    else:
        credentials = service_account.Credentials.from_service_account_info(
            st.secrets["gcp_service_account"]
        )
        _client = bigquery.Client(project=project, credentials=credentials)

    return _client


def get_dataset() -> str:
    return os.environ.get("BQ_DATASET") or st.secrets.get("BQ_DATASET", "startup_pulse")


def query_df(sql: str) -> pd.DataFrame:
    """Run a SQL query and return results as a DataFrame."""
    return get_client().query(sql).to_dataframe()
```

**Step 2: Create Streamlit config**

File: `streamlit_app/.streamlit/config.toml`

```toml
[theme]
primaryColor = "#4F8BF9"
backgroundColor = "#FFFFFF"
secondaryBackgroundColor = "#F0F2F6"
textColor = "#262730"
```

**Step 3: Commit**

```bash
git add streamlit_app/utils/bq_client.py streamlit_app/.streamlit/config.toml
git commit -m "Support Streamlit Cloud secrets for BigQuery auth"
```

---

### Task 4: Add requirements.txt at project root for Streamlit Cloud

**Files:**
- The Streamlit Cloud deployer looks for requirements at the app's directory level. `streamlit_app/requirements.txt` already exists and has the right deps. Streamlit Cloud needs to know the app entry point — this is configured in their UI, not in code.

No file changes needed. This task is a configuration note for the setup guide (Task 5).

---

### Task 5: Update SETUP_GUIDE.md with Cloud Deployment + Local Swap-Back

**Files:**
- Modify: `SETUP_GUIDE.md`

Add two new sections:
- Section 12: Cloud Deployment (GitHub Actions + Streamlit Cloud)
- Section 13: Switching Between Local and Cloud

**Step 1: Add Section 12 — Cloud Deployment**

Covers:
- Adding GitHub secrets (GCP_SA_KEY, GCP_PROJECT_ID, BQ_DATASET)
- Deploying Streamlit to Streamlit Community Cloud
- Manually triggering the pipeline
- Monitoring runs

**Step 2: Add Section 13 — Switching Between Local and Cloud**

Covers:
- Both modes use the same BigQuery tables and same scraper code
- Local: `make up` to start Docker Compose with Airflow
- Cloud: GitHub Actions on cron, Streamlit Community Cloud for dashboard
- How to disable one when using the other (pause DAG / disable workflow)

**Step 3: Update Table of Contents**

Add entries 12 and 13.

**Step 4: Commit**

```bash
git add SETUP_GUIDE.md
git commit -m "Add cloud deployment and local swap-back guides"
```

---

### Task 6: Update README.md

**Files:**
- Modify: `README.md`

Add a brief "Deployment" section noting both local (Docker Compose) and cloud (GitHub Actions + Streamlit Cloud) options, linking to the setup guide for details.

**Step 1: Add deployment section after Quick Start**

**Step 2: Commit**

```bash
git add README.md
git commit -m "Add deployment options to README"
```

---

## Execution Order

```
Task 1 (runner script) → Task 2 (GitHub Actions) → Task 3 (Streamlit Cloud auth)
→ Task 4 (no-op, config note) → Task 5 (setup guide) → Task 6 (README)
```

All tasks are sequential. Final state: push to main, then configure secrets in GitHub and deploy on Streamlit Cloud.
