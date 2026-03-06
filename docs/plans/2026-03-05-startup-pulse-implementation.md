# Startup Pulse Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Transform the reddit-trends repo into startup-pulse — a startup job market intelligence platform that scrapes YC, Wellfound, and HN job postings daily, extracts skills/market signals via NLP, loads to BigQuery, and visualizes trends in Streamlit.

**Architecture:** Three parallel Playwright/API scrapers feed into a shared normalizer, then fork to skill extraction (TF-IDF + taxonomy) and market metrics aggregation before loading to BigQuery. Streamlit reads directly from BigQuery for dashboarding.

**Tech Stack:** Python 3.11, Playwright, BeautifulSoup, NLTK, scikit-learn, Airflow 2.11, BigQuery, Streamlit, Plotly, Docker Compose.

---

## Task 1: Update Config and Project Identity

**Files:**
- Modify: `src/utils/config.py` (full rewrite)
- Modify: `.env.example` (remove Reddit vars, keep GCP vars)
- Modify: `docker-compose.yml:10-12` (remove REDDIT_* env vars)

**Step 1: Rewrite config.py**

Replace the entire file with job-board configuration:

```python
"""Centralized configuration for the Startup Pulse pipeline."""

# -- Data source URLs --------------------------------------------------------
YC_JOBS_URL = "https://www.workatastartup.com/jobs"
WELLFOUND_JOBS_URL = "https://wellfound.com/jobs"
HN_API_BASE = "https://hacker-news.firebaseio.com/v0"

# -- Scraping settings -------------------------------------------------------
SCRAPE_TIMEOUT_MS = 60_000          # Playwright page timeout
SCRAPE_MAX_PAGES = 10               # Max pagination depth per source
SCRAPE_DELAY_SECONDS = 2            # Polite delay between page loads

# -- NLP settings ------------------------------------------------------------
TFIDF_MAX_FEATURES = 300
TFIDF_NGRAM_RANGE = (1, 2)
TFIDF_MIN_DF = 2
TFIDF_MAX_DF = 0.85
MAX_SKILLS_PER_CATEGORY = 50

# -- Skill taxonomy ----------------------------------------------------------
# Curated list of tech skills to match in job descriptions.
# Grouped by category for dashboard filtering.
SKILL_TAXONOMY = {
    "languages": [
        "python", "javascript", "typescript", "java", "go", "rust", "ruby",
        "c++", "c#", "swift", "kotlin", "scala", "php", "sql", "r",
    ],
    "frameworks": [
        "react", "next.js", "vue", "angular", "django", "flask", "fastapi",
        "spring", "rails", "express", "node.js", "svelte", "remix",
    ],
    "infra_and_cloud": [
        "aws", "gcp", "azure", "docker", "kubernetes", "terraform",
        "ansible", "jenkins", "github actions", "circleci", "datadog",
    ],
    "data_and_ml": [
        "pytorch", "tensorflow", "pandas", "spark", "airflow", "dbt",
        "snowflake", "bigquery", "redshift", "kafka", "redis", "postgresql",
        "mongodb", "elasticsearch", "llm", "rag", "langchain", "openai",
    ],
}

# -- Role categories ---------------------------------------------------------
ROLE_CATEGORIES = {
    "backend": ["backend", "server", "api", "microservice", "systems"],
    "frontend": ["frontend", "front-end", "ui", "ux", "web"],
    "fullstack": ["fullstack", "full-stack", "full stack"],
    "ml_ai": ["machine learning", "ml ", "ai ", "data scientist", "deep learning",
              "nlp", "computer vision", "llm"],
    "data_eng": ["data engineer", "analytics engineer", "etl", "data platform",
                 "data infrastructure"],
    "devops_sre": ["devops", "sre", "infrastructure", "platform engineer",
                   "reliability", "cloud engineer"],
    "mobile": ["ios", "android", "mobile", "react native", "flutter"],
}

# -- Seniority levels --------------------------------------------------------
SENIORITY_KEYWORDS = {
    "intern": ["intern", "internship"],
    "junior": ["junior", "jr.", "entry level", "new grad", "associate"],
    "mid": ["mid-level", "mid level", "intermediate"],
    "senior": ["senior", "sr.", "experienced"],
    "staff": ["staff", "principal", "distinguished"],
    "lead": ["lead", "tech lead", "team lead", "engineering manager"],
    "director": ["director", "vp", "head of"],
}

# -- BigQuery settings -------------------------------------------------------
BQ_LOCATION = "US"
```

**Step 2: Update .env.example**

```
GCP_PROJECT_ID=your-gcp-project-id
BQ_DATASET=startup_pulse
AIRFLOW_UID=50000
```

**Step 3: Update docker-compose.yml**

Remove lines 10-12 (REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, REDDIT_USER_AGENT) from the x-airflow-common environment block.

**Step 4: Commit**

```bash
git add src/utils/config.py .env.example docker-compose.yml
git commit -m "Pivot config from Reddit to startup job board sources"
```

---

## Task 2: Add Playwright to Docker and Dependencies

**Files:**
- Modify: `airflow/Dockerfile` (add Playwright install)
- Modify: `airflow/requirements.txt` (swap praw for playwright + beautifulsoup4)

**Step 1: Update airflow/Dockerfile**

```dockerfile
FROM apache/airflow:2.11.0-python3.11

USER root

# Install system deps for Playwright Chromium
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        libnss3 libnspr4 libdbus-1-3 libatk1.0-0 libatk-bridge2.0-0 \
        libcups2 libdrm2 libxkbcommon0 libatspi2.0-0 libxcomposite1 \
        libxdamage1 libxfixes3 libxrandr2 libgbm1 libpango-1.0-0 \
        libcairo2 libasound2 libwayland-client0 && \
    rm -rf /var/lib/apt/lists/*

USER airflow

COPY requirements.txt /tmp/requirements.txt

RUN pip install --no-cache-dir -r /tmp/requirements.txt && \
    playwright install chromium

ENV PYTHONPATH=/opt/airflow:${PYTHONPATH}
```

**Step 2: Update airflow/requirements.txt**

```
playwright>=1.40.0
beautifulsoup4>=4.12.0
requests>=2.31.0
google-cloud-bigquery[pandas,pyarrow]>=3.20.0
pandas>=2.0.0
nltk>=3.8.0
scikit-learn>=1.3.0
db-dtypes>=1.1.0
```

**Step 3: Commit**

```bash
git add airflow/Dockerfile airflow/requirements.txt
git commit -m "Add Playwright and BeautifulSoup deps, remove PRAW"
```

---

## Task 3: Build HN "Who is Hiring?" Scraper

Start with HN because it uses a free API (no Playwright needed), making it the easiest to test.

**Files:**
- Create: `src/extract/__init__.py` (already exists, keep)
- Create: `src/extract/hn_scraper.py`
- Create: `tests/test_hn_scraper.py`
- Delete: `src/extract/reddit_collector.py`

**Step 1: Write the failing test**

```python
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

    def test_parse_hn_comment_returns_none_for_non_job(self):
        scraper = HNScraper()
        non_job = {"id": 1, "text": "Is anyone else having trouble with the thread?", "type": "comment", "by": "user", "parent": 99000, "time": 1709251200}
        assert scraper._parse_comment(non_job) is None
```

**Step 2: Run test to verify it fails**

Run: `cd /home/konsing/reddit-trends && python -m pytest tests/test_hn_scraper.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.extract.hn_scraper'`

**Step 3: Write hn_scraper.py**

```python
# src/extract/hn_scraper.py
"""Hacker News 'Who is Hiring?' scraper.

Fetches the latest monthly hiring thread via the HN Firebase API,
parses each top-level comment into a structured job posting dict.
"""

import hashlib
import html
import json
import logging
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

from src.utils.config import HN_API_BASE

logger = logging.getLogger(__name__)

_HN_SEARCH_URL = "https://hn.algolia.com/api/v1/search"
_REQUEST_TIMEOUT = 30


class HNScraper:
    """Scrapes job postings from HN 'Who is Hiring?' threads."""

    def scrape(self, output_dir: str) -> dict:
        """Fetch the latest hiring thread and parse all job comments.

        Args:
            output_dir: Directory where ``jobs.json`` will be written.

        Returns:
            Metadata dict with ``total_jobs`` and ``thread_id``.
        """
        thread_id = self._find_latest_thread()
        if thread_id is None:
            logger.warning("No 'Who is Hiring?' thread found.")
            return {"total_jobs": 0, "thread_id": None}

        logger.info("Found hiring thread: %d", thread_id)

        comment_ids = self._get_kid_ids(thread_id)
        logger.info("Thread has %d top-level comments", len(comment_ids))

        jobs = []
        for cid in comment_ids:
            comment = self._fetch_item(cid)
            if comment is None or comment.get("deleted") or comment.get("dead"):
                continue
            parsed = self._parse_comment(comment)
            if parsed is not None:
                jobs.append(parsed)
            time.sleep(0.05)  # gentle rate limit

        Path(output_dir).mkdir(parents=True, exist_ok=True)
        output_path = os.path.join(output_dir, "jobs.json")
        with open(output_path, "w", encoding="utf-8") as fh:
            json.dump(jobs, fh, ensure_ascii=False, indent=2)

        logger.info("Wrote %d HN jobs to %s", len(jobs), output_path)
        return {"total_jobs": len(jobs), "thread_id": thread_id}

    # -- Private helpers ------------------------------------------------------

    def _find_latest_thread(self) -> int | None:
        """Search Algolia for the most recent 'Who is Hiring?' thread."""
        params = {
            "query": "Ask HN: Who is hiring?",
            "tags": "ask_hn",
            "restrictSearchableAttributes": "title",
            "hitsPerPage": 1,
        }
        resp = requests.get(_HN_SEARCH_URL, params=params, timeout=_REQUEST_TIMEOUT)
        resp.raise_for_status()
        hits = resp.json().get("hits", [])
        if not hits:
            return None
        return int(hits[0]["objectID"])

    def _get_kid_ids(self, item_id: int) -> list[int]:
        """Fetch direct child comment IDs for a given item."""
        item = self._fetch_item(item_id)
        return item.get("kids", []) if item else []

    def _fetch_item(self, item_id: int) -> dict | None:
        """Fetch a single HN item by ID."""
        url = f"{HN_API_BASE}/item/{item_id}.json"
        try:
            resp = requests.get(url, timeout=_REQUEST_TIMEOUT)
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as exc:
            logger.warning("Failed to fetch item %d: %s", item_id, exc)
            return None

    def _parse_comment(self, comment: dict) -> dict | None:
        """Parse an HN comment into a structured job dict.

        HN hiring comments typically follow the format:
            Company | Role | Location | REMOTE | Salary

        Returns None if the comment doesn't look like a job posting.
        """
        raw_text = comment.get("text", "")
        if not raw_text:
            return None

        # Decode HTML entities
        text = html.unescape(raw_text)
        # Strip HTML tags for plain text
        plain = re.sub(r"<[^>]+>", "\n", text).strip()

        # First line is usually "Company | Role | Location | ..."
        first_line = plain.split("\n")[0].strip()
        parts = [p.strip() for p in first_line.split("|")]

        # Must have at least 2 pipe-separated fields to look like a job
        if len(parts) < 2:
            return None

        company = parts[0]
        title = parts[1] if len(parts) > 1 else ""
        location_parts = parts[2:] if len(parts) > 2 else []
        location_str = ", ".join(location_parts)

        # Detect remote
        remote = bool(re.search(r"\bremote\b", location_str, re.IGNORECASE))

        # Build unique job_id from comment id
        job_id = f"hn_{comment['id']}"

        return {
            "job_id": job_id,
            "source": "hackernews",
            "company": company,
            "title": title,
            "description": plain,
            "salary_min": None,
            "salary_max": None,
            "currency": None,
            "location": location_str,
            "remote": remote,
            "company_stage": None,
            "yc_batch": None,
            "equity": None,
            "url": f"https://news.ycombinator.com/item?id={comment['id']}",
            "collected_at": datetime.now(timezone.utc).isoformat(),
        }
```

**Step 4: Run tests to verify they pass**

Run: `cd /home/konsing/reddit-trends && python -m pytest tests/test_hn_scraper.py -v`
Expected: All 6 tests PASS

**Step 5: Delete old Reddit collector**

```bash
rm src/extract/reddit_collector.py
```

**Step 6: Commit**

```bash
git add src/extract/hn_scraper.py tests/test_hn_scraper.py
git rm src/extract/reddit_collector.py
git commit -m "Add HN Who is Hiring scraper, remove Reddit collector"
```

---

## Task 4: Build YC Work at a Startup Scraper

**Files:**
- Create: `src/extract/yc_scraper.py`
- Create: `tests/test_yc_scraper.py`

**Step 1: Write the failing test**

```python
# tests/test_yc_scraper.py
"""Tests for the YC Work at a Startup scraper."""

from src.extract.yc_scraper import YCScraper


SAMPLE_RAW_JOB = {
    "title": "Senior Software Engineer",
    "company": "Acme AI",
    "location": "San Francisco, CA",
    "salary": "$150K - $200K",
    "description": "Build ML pipelines using Python and PyTorch.",
    "url": "https://www.workatastartup.com/jobs/12345",
    "batch": "S24",
}


class TestYCScraper:
    def test_normalize_job_sets_source(self):
        scraper = YCScraper()
        job = scraper._normalize(SAMPLE_RAW_JOB)
        assert job["source"] == "yc_wats"

    def test_normalize_job_generates_job_id(self):
        scraper = YCScraper()
        job = scraper._normalize(SAMPLE_RAW_JOB)
        assert job["job_id"].startswith("yc_")

    def test_normalize_job_preserves_batch(self):
        scraper = YCScraper()
        job = scraper._normalize(SAMPLE_RAW_JOB)
        assert job["yc_batch"] == "S24"

    def test_normalize_job_parses_salary_range(self):
        scraper = YCScraper()
        job = scraper._normalize(SAMPLE_RAW_JOB)
        assert job["salary_min"] == 150000
        assert job["salary_max"] == 200000
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_yc_scraper.py -v`
Expected: FAIL — `ModuleNotFoundError`

**Step 3: Write yc_scraper.py**

```python
# src/extract/yc_scraper.py
"""Work at a Startup (YC) job scraper using Playwright.

Navigates the JS-rendered job listing pages, extracts job cards,
and normalizes them into the shared job schema.
"""

import hashlib
import json
import logging
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path

from src.utils.config import YC_JOBS_URL, SCRAPE_DELAY_SECONDS, SCRAPE_MAX_PAGES, SCRAPE_TIMEOUT_MS

logger = logging.getLogger(__name__)


class YCScraper:
    """Scrapes job listings from workatastartup.com."""

    def scrape(self, output_dir: str) -> dict:
        """Launch a headless browser, paginate through listings, and save.

        Args:
            output_dir: Directory where ``jobs.json`` will be written.

        Returns:
            Metadata dict with ``total_jobs``.
        """
        from playwright.sync_api import sync_playwright

        raw_jobs = []

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.set_default_timeout(SCRAPE_TIMEOUT_MS)

            page.goto(YC_JOBS_URL)
            page.wait_for_load_state("networkidle")

            for page_num in range(SCRAPE_MAX_PAGES):
                logger.info("YC scrape: page %d", page_num + 1)
                cards = self._extract_cards(page)
                if not cards:
                    break
                raw_jobs.extend(cards)

                # Try to click next / load more
                if not self._load_next_page(page):
                    break
                time.sleep(SCRAPE_DELAY_SECONDS)

            browser.close()

        jobs = [self._normalize(raw) for raw in raw_jobs]

        Path(output_dir).mkdir(parents=True, exist_ok=True)
        output_path = os.path.join(output_dir, "jobs.json")
        with open(output_path, "w", encoding="utf-8") as fh:
            json.dump(jobs, fh, ensure_ascii=False, indent=2)

        logger.info("Wrote %d YC jobs to %s", len(jobs), output_path)
        return {"total_jobs": len(jobs)}

    # -- Private helpers ------------------------------------------------------

    def _extract_cards(self, page) -> list[dict]:
        """Extract job card data from the current page DOM."""
        cards = []
        job_elements = page.query_selector_all("[class*='job'], [class*='listing'], [data-job]")

        for el in job_elements:
            try:
                title_el = el.query_selector("h2, h3, [class*='title']")
                company_el = el.query_selector("[class*='company'], [class*='org']")
                location_el = el.query_selector("[class*='location']")
                salary_el = el.query_selector("[class*='salary'], [class*='compensation']")
                link_el = el.query_selector("a[href*='/jobs/']")
                batch_el = el.query_selector("[class*='batch']")

                card = {
                    "title": title_el.inner_text().strip() if title_el else "",
                    "company": company_el.inner_text().strip() if company_el else "",
                    "location": location_el.inner_text().strip() if location_el else "",
                    "salary": salary_el.inner_text().strip() if salary_el else "",
                    "description": el.inner_text().strip(),
                    "url": link_el.get_attribute("href") if link_el else "",
                    "batch": batch_el.inner_text().strip() if batch_el else "",
                }

                if card["title"] and card["company"]:
                    cards.append(card)
            except Exception as exc:
                logger.debug("Failed to parse YC card: %s", exc)
                continue

        return cards

    def _load_next_page(self, page) -> bool:
        """Attempt to load the next page of results. Returns False if no more."""
        try:
            next_btn = page.query_selector("button:has-text('Load more'), button:has-text('Next'), [class*='next']")
            if next_btn and next_btn.is_visible():
                next_btn.click()
                page.wait_for_load_state("networkidle")
                return True
        except Exception:
            pass
        return False

    def _normalize(self, raw: dict) -> dict:
        """Normalize a raw scraped job into the shared schema."""
        salary_min, salary_max = self._parse_salary(raw.get("salary", ""))

        # Generate stable job_id from company + title + url
        id_str = f"{raw.get('company', '')}-{raw.get('title', '')}-{raw.get('url', '')}"
        job_id = f"yc_{hashlib.md5(id_str.encode()).hexdigest()[:12]}"

        url = raw.get("url", "")
        if url and not url.startswith("http"):
            url = f"https://www.workatastartup.com{url}"

        return {
            "job_id": job_id,
            "source": "yc_wats",
            "company": raw.get("company", ""),
            "title": raw.get("title", ""),
            "description": raw.get("description", ""),
            "salary_min": salary_min,
            "salary_max": salary_max,
            "currency": "USD" if salary_min else None,
            "location": raw.get("location", ""),
            "remote": bool(re.search(r"\bremote\b", raw.get("location", ""), re.IGNORECASE)),
            "company_stage": None,
            "yc_batch": raw.get("batch") or None,
            "equity": None,
            "url": url,
            "collected_at": datetime.now(timezone.utc).isoformat(),
        }

    @staticmethod
    def _parse_salary(text: str) -> tuple[int | None, int | None]:
        """Extract min/max salary from strings like '$150K - $200K' or '$150,000 - $200,000'."""
        if not text:
            return None, None

        # Match patterns like $150K, $150k, $150,000
        amounts = re.findall(r"\$\s*([\d,]+)\s*[kK]?", text)
        if len(amounts) < 1:
            return None, None

        parsed = []
        for amt in amounts:
            num = int(amt.replace(",", ""))
            if num < 1000:
                num *= 1000  # $150K -> 150000
            parsed.append(num)

        if len(parsed) == 1:
            return parsed[0], parsed[0]
        return parsed[0], parsed[1]
```

**Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_yc_scraper.py -v`
Expected: All 4 tests PASS

**Step 5: Commit**

```bash
git add src/extract/yc_scraper.py tests/test_yc_scraper.py
git commit -m "Add YC Work at a Startup scraper with Playwright"
```

---

## Task 5: Build Wellfound Scraper

**Files:**
- Create: `src/extract/wellfound_scraper.py`
- Create: `tests/test_wellfound_scraper.py`

**Step 1: Write the failing test**

```python
# tests/test_wellfound_scraper.py
"""Tests for the Wellfound job scraper."""

from src.extract.wellfound_scraper import WellfoundScraper


SAMPLE_RAW_JOB = {
    "title": "ML Engineer",
    "company": "DataCo",
    "location": "Remote (US)",
    "salary": "$120k – $180k",
    "equity": "0.5% - 1.0%",
    "stage": "Series A",
    "description": "Build recommendation systems.",
    "url": "https://wellfound.com/l/dataco-ml-engineer",
}


class TestWellfoundScraper:
    def test_normalize_sets_source(self):
        scraper = WellfoundScraper()
        job = scraper._normalize(SAMPLE_RAW_JOB)
        assert job["source"] == "wellfound"

    def test_normalize_extracts_equity(self):
        scraper = WellfoundScraper()
        job = scraper._normalize(SAMPLE_RAW_JOB)
        assert job["equity"] == "0.5% - 1.0%"

    def test_normalize_extracts_company_stage(self):
        scraper = WellfoundScraper()
        job = scraper._normalize(SAMPLE_RAW_JOB)
        assert job["company_stage"] == "Series A"

    def test_normalize_detects_remote(self):
        scraper = WellfoundScraper()
        job = scraper._normalize(SAMPLE_RAW_JOB)
        assert job["remote"] is True

    def test_normalize_parses_salary(self):
        scraper = WellfoundScraper()
        job = scraper._normalize(SAMPLE_RAW_JOB)
        assert job["salary_min"] == 120000
        assert job["salary_max"] == 180000
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_wellfound_scraper.py -v`
Expected: FAIL

**Step 3: Write wellfound_scraper.py**

```python
# src/extract/wellfound_scraper.py
"""Wellfound (formerly AngelList Talent) job scraper using Playwright.

Navigates Wellfound job listings, extracts job cards including
equity and company stage data unique to this source.
"""

import hashlib
import json
import logging
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path

from src.utils.config import WELLFOUND_JOBS_URL, SCRAPE_DELAY_SECONDS, SCRAPE_MAX_PAGES, SCRAPE_TIMEOUT_MS

logger = logging.getLogger(__name__)


class WellfoundScraper:
    """Scrapes job listings from wellfound.com."""

    def scrape(self, output_dir: str) -> dict:
        """Launch a headless browser, paginate through listings, and save.

        Args:
            output_dir: Directory where ``jobs.json`` will be written.

        Returns:
            Metadata dict with ``total_jobs``.
        """
        from playwright.sync_api import sync_playwright

        raw_jobs = []

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.set_default_timeout(SCRAPE_TIMEOUT_MS)

            page.goto(WELLFOUND_JOBS_URL)
            page.wait_for_load_state("networkidle")

            for page_num in range(SCRAPE_MAX_PAGES):
                logger.info("Wellfound scrape: page %d", page_num + 1)
                cards = self._extract_cards(page)
                if not cards:
                    break
                raw_jobs.extend(cards)

                if not self._load_next_page(page):
                    break
                time.sleep(SCRAPE_DELAY_SECONDS)

            browser.close()

        jobs = [self._normalize(raw) for raw in raw_jobs]

        Path(output_dir).mkdir(parents=True, exist_ok=True)
        output_path = os.path.join(output_dir, "jobs.json")
        with open(output_path, "w", encoding="utf-8") as fh:
            json.dump(jobs, fh, ensure_ascii=False, indent=2)

        logger.info("Wrote %d Wellfound jobs to %s", len(jobs), output_path)
        return {"total_jobs": len(jobs)}

    def _extract_cards(self, page) -> list[dict]:
        """Extract job card data from the current page DOM."""
        cards = []
        job_elements = page.query_selector_all("[class*='job'], [class*='listing'], [data-test='startup-list-item']")

        for el in job_elements:
            try:
                title_el = el.query_selector("h2, h3, [class*='title']")
                company_el = el.query_selector("[class*='company'], [class*='startup-name']")
                location_el = el.query_selector("[class*='location']")
                salary_el = el.query_selector("[class*='salary'], [class*='compensation']")
                equity_el = el.query_selector("[class*='equity']")
                stage_el = el.query_selector("[class*='stage'], [class*='size']")
                link_el = el.query_selector("a[href*='/l/'], a[href*='/jobs/']")

                card = {
                    "title": title_el.inner_text().strip() if title_el else "",
                    "company": company_el.inner_text().strip() if company_el else "",
                    "location": location_el.inner_text().strip() if location_el else "",
                    "salary": salary_el.inner_text().strip() if salary_el else "",
                    "equity": equity_el.inner_text().strip() if equity_el else "",
                    "stage": stage_el.inner_text().strip() if stage_el else "",
                    "description": el.inner_text().strip(),
                    "url": link_el.get_attribute("href") if link_el else "",
                }

                if card["title"] and card["company"]:
                    cards.append(card)
            except Exception as exc:
                logger.debug("Failed to parse Wellfound card: %s", exc)
                continue

        return cards

    def _load_next_page(self, page) -> bool:
        """Attempt to load the next page of results."""
        try:
            next_btn = page.query_selector("button:has-text('Next'), a:has-text('Next'), [class*='next']")
            if next_btn and next_btn.is_visible():
                next_btn.click()
                page.wait_for_load_state("networkidle")
                return True
        except Exception:
            pass
        return False

    def _normalize(self, raw: dict) -> dict:
        """Normalize a raw scraped job into the shared schema."""
        salary_min, salary_max = self._parse_salary(raw.get("salary", ""))

        id_str = f"{raw.get('company', '')}-{raw.get('title', '')}-{raw.get('url', '')}"
        job_id = f"wf_{hashlib.md5(id_str.encode()).hexdigest()[:12]}"

        url = raw.get("url", "")
        if url and not url.startswith("http"):
            url = f"https://wellfound.com{url}"

        return {
            "job_id": job_id,
            "source": "wellfound",
            "company": raw.get("company", ""),
            "title": raw.get("title", ""),
            "description": raw.get("description", ""),
            "salary_min": salary_min,
            "salary_max": salary_max,
            "currency": "USD" if salary_min else None,
            "location": raw.get("location", ""),
            "remote": bool(re.search(r"\bremote\b", raw.get("location", ""), re.IGNORECASE)),
            "company_stage": raw.get("stage") or None,
            "yc_batch": None,
            "equity": raw.get("equity") or None,
            "url": url,
            "collected_at": datetime.now(timezone.utc).isoformat(),
        }

    @staticmethod
    def _parse_salary(text: str) -> tuple[int | None, int | None]:
        """Extract min/max salary from strings like '$120k - $180k'."""
        if not text:
            return None, None

        amounts = re.findall(r"\$\s*([\d,]+)\s*[kK]?", text)
        if len(amounts) < 1:
            return None, None

        parsed = []
        for amt in amounts:
            num = int(amt.replace(",", ""))
            if num < 1000:
                num *= 1000
            parsed.append(num)

        if len(parsed) == 1:
            return parsed[0], parsed[0]
        return parsed[0], parsed[1]
```

**Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_wellfound_scraper.py -v`
Expected: All 5 tests PASS

**Step 5: Commit**

```bash
git add src/extract/wellfound_scraper.py tests/test_wellfound_scraper.py
git commit -m "Add Wellfound job scraper with equity and stage extraction"
```

---

## Task 6: Update Transform Layer — Text Cleaner for Job Descriptions

**Files:**
- Modify: `src/transform/text_cleaner.py` (adapt stop words and clean method)
- Create: `tests/test_text_cleaner.py`

**Step 1: Write the failing test**

```python
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
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_text_cleaner.py -v`
Expected: FAIL (clean_jobs method doesn't exist yet)

**Step 3: Rewrite text_cleaner.py**

Replace the full file — change stop words from Reddit-specific to job-posting-specific, rename `clean_posts` to `clean_jobs`, adapt field names:

```python
# src/transform/text_cleaner.py
"""Text cleaning and preprocessing for job descriptions.

Downloads required NLTK data, removes noise (HTML, URLs, special
characters), tokenizes, removes stop words, and lemmatizes.
"""

import json
import logging
import re
from pathlib import Path

import nltk
from nltk.corpus import stopwords
from nltk.stem import WordNetLemmatizer
from nltk.tokenize import word_tokenize

logger = logging.getLogger(__name__)

JOB_STOP_WORDS = {
    "amp", "nbsp", "http", "https", "www", "com", "org",
    "apply", "click", "email", "send", "resume", "cover", "letter",
    "please", "position", "candidate", "applicant", "role",
    "company", "team", "join", "work", "working",
    "just", "like", "also", "would", "one", "get", "got",
    "even", "much", "thing", "really", "well",
}


class TextCleaner:
    """Clean and normalize job posting text for downstream NLP tasks."""

    def __init__(self) -> None:
        nltk.download("stopwords", quiet=True)
        nltk.download("punkt", quiet=True)
        nltk.download("punkt_tab", quiet=True)
        nltk.download("wordnet", quiet=True)

        self.stop_words = set(stopwords.words("english")) | JOB_STOP_WORDS
        self.lemmatizer = WordNetLemmatizer()
        logger.info("TextCleaner initialized with %d stop words", len(self.stop_words))

    def clean_text(self, text: str) -> str:
        """Clean a single text string through the full NLP pipeline."""
        if not text:
            return ""

        text = text.lower()
        text = re.sub(r"<[^>]+>", " ", text)              # Remove HTML tags
        text = re.sub(r"https?://\S+", "", text)           # Remove URLs
        text = re.sub(r"www\.\S+", "", text)
        text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)  # Markdown links
        text = re.sub(r"[^a-zA-Z0-9+#.\s]", "", text)     # Keep +, #, . for C++, C#, etc.
        text = re.sub(r"\s+", " ", text).strip()

        tokens = word_tokenize(text)
        tokens = [t for t in tokens if t not in self.stop_words and len(t) > 1]
        tokens = [self.lemmatizer.lemmatize(t) for t in tokens]

        return " ".join(tokens)

    def clean_jobs(self, jobs: list[dict]) -> list[dict]:
        """Clean description fields on a list of job dicts.

        Adds ``cleaned_description`` to each job dict. Returns the
        modified list (mutates in place).
        """
        for job in jobs:
            job["cleaned_description"] = self.clean_text(job.get("description", ""))

        jobs_with_content = sum(1 for j in jobs if j["cleaned_description"])
        logger.info("Cleaned %d jobs (%d with content)", len(jobs), jobs_with_content)
        return jobs
```

**Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_text_cleaner.py -v`
Expected: All 5 tests PASS

**Step 5: Commit**

```bash
git add src/transform/text_cleaner.py tests/test_text_cleaner.py
git commit -m "Adapt text cleaner from Reddit posts to job descriptions"
```

---

## Task 7: Build Skill Extractor (replaces keyword_extractor.py)

**Files:**
- Modify: `src/transform/keyword_extractor.py` → rename to `src/extract/` no, keep path: `src/transform/skill_extractor.py`
- Delete: `src/transform/keyword_extractor.py`
- Create: `tests/test_skill_extractor.py`

**Step 1: Write the failing test**

```python
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
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_skill_extractor.py -v`
Expected: FAIL

**Step 3: Write skill_extractor.py**

```python
# src/transform/skill_extractor.py
"""Skill extraction from job descriptions.

Combines TF-IDF keyword extraction with curated taxonomy matching
to identify in-demand technical skills and compute salary correlations.
"""

import json
import logging
import re
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer

from src.utils.config import (
    MAX_SKILLS_PER_CATEGORY,
    SKILL_TAXONOMY,
    TFIDF_MAX_DF,
    TFIDF_MAX_FEATURES,
    TFIDF_MIN_DF,
    TFIDF_NGRAM_RANGE,
)

logger = logging.getLogger(__name__)


class SkillExtractor:
    """Extract technical skills from cleaned job descriptions."""

    def __init__(self) -> None:
        # Flatten taxonomy for quick lookup: skill -> category
        self._skill_to_category: dict[str, str] = {}
        for category, skills in SKILL_TAXONOMY.items():
            for skill in skills:
                self._skill_to_category[skill.lower()] = category

    def extract(self, jobs: list[dict]) -> list[dict]:
        """Extract skill trend records from a list of cleaned job dicts.

        Returns:
            List of skill trend dicts with keys: skill, category,
            frequency, tfidf_score, avg_salary, num_jobs.
        """
        if not jobs:
            return []

        # Taxonomy matching across all jobs
        skill_jobs: dict[str, list[dict]] = defaultdict(list)
        for job in jobs:
            desc = job.get("cleaned_description", "")
            matched = self._taxonomy_match(desc)
            for skill in matched:
                skill_jobs[skill].append(job)

        # TF-IDF for additional signal
        descriptions = [j.get("cleaned_description", "") for j in jobs]
        descriptions = [d for d in descriptions if d.strip()]

        tfidf_scores: dict[str, float] = {}
        if len(descriptions) >= 2:
            try:
                vectorizer = TfidfVectorizer(
                    max_features=TFIDF_MAX_FEATURES,
                    ngram_range=TFIDF_NGRAM_RANGE,
                    min_df=TFIDF_MIN_DF,
                    max_df=TFIDF_MAX_DF,
                )
                matrix = vectorizer.fit_transform(descriptions)
                feature_names = vectorizer.get_feature_names_out()
                avg_scores = np.asarray(matrix.mean(axis=0)).flatten()
                tfidf_scores = dict(zip(feature_names, avg_scores))
            except ValueError as exc:
                logger.warning("TF-IDF failed: %s", exc)

        # Build results
        results = []
        for skill, matching_jobs in skill_jobs.items():
            category = self._skill_to_category.get(skill, "other")
            salaries = [
                (j["salary_min"] + j["salary_max"]) / 2
                for j in matching_jobs
                if j.get("salary_min") and j.get("salary_max")
            ]

            results.append({
                "skill": skill,
                "category": category,
                "frequency": len(matching_jobs),
                "tfidf_score": float(tfidf_scores.get(skill, 0.0)),
                "avg_salary": float(np.mean(salaries)) if salaries else None,
                "num_jobs": len(jobs),
            })

        results.sort(key=lambda r: r["frequency"], reverse=True)
        logger.info("Extracted %d skills from %d jobs", len(results), len(jobs))
        return results

    def _taxonomy_match(self, text: str) -> set[str]:
        """Match curated skills against text using word boundary regex."""
        found = set()
        text_lower = text.lower()
        for skill in self._skill_to_category:
            # Use word boundary for single words, substring for multi-word
            if " " in skill:
                if skill in text_lower:
                    found.add(skill)
            else:
                if re.search(rf"\b{re.escape(skill)}\b", text_lower):
                    found.add(skill)
        return found
```

**Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_skill_extractor.py -v`
Expected: All 3 tests PASS

**Step 5: Delete old keyword_extractor.py**

```bash
rm src/transform/keyword_extractor.py
```

**Step 6: Commit**

```bash
git add src/transform/skill_extractor.py tests/test_skill_extractor.py
git rm src/transform/keyword_extractor.py
git commit -m "Add skill extractor with taxonomy matching and salary correlation"
```

---

## Task 8: Update Metrics Aggregator for Job Market Data

**Files:**
- Modify: `src/transform/metrics_aggregator.py` (adapt from subreddit to job market metrics)
- Create: `tests/test_metrics_aggregator.py`

**Step 1: Write the failing test**

```python
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
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_metrics_aggregator.py -v`
Expected: FAIL (aggregate signature changed)

**Step 3: Rewrite metrics_aggregator.py**

```python
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
```

**Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_metrics_aggregator.py -v`
Expected: All 3 tests PASS

**Step 5: Commit**

```bash
git add src/transform/metrics_aggregator.py tests/test_metrics_aggregator.py
git commit -m "Adapt metrics aggregator for job market data with salary and remote stats"
```

---

## Task 9: Update BigQuery Schema and Loader

**Files:**
- Modify: `scripts/init_bigquery.py` (new table schemas)
- Modify: `src/load/bigquery_loader.py` (adapt field names and validation)
- Modify: `src/utils/deduplication.py` (change post_id to job_id)

**Step 1: Rewrite init_bigquery.py with new schemas**

Replace the three table schemas (raw_posts → raw_jobs, keyword_trends → skill_trends, subreddit_metrics → market_metrics) matching the design doc exactly. Keep the `_create_table` helper and `exists_ok=True` pattern.

**Step 2: Update bigquery_loader.py**

- Rename `load_posts` → `load_jobs`, change `post_id` refs to `job_id`
- Rename `load_keywords` → `load_skills`
- Keep `load_metrics` but update field validation
- Update `load_all` to use new method names and accept jobs/skills/metrics paths
- Remove `selftext` truncation, add `description` truncation to 10K chars

**Step 3: Update deduplication.py**

- Change `post_id` → `job_id` in both `deduplicate_in_run` and `get_existing_post_ids` (rename to `get_existing_job_ids`)
- Remove `listing_type` merge logic (not relevant for jobs)

**Step 4: Commit**

```bash
git add scripts/init_bigquery.py src/load/bigquery_loader.py src/utils/deduplication.py
git commit -m "Update BigQuery schema and loader for job market tables"
```

---

## Task 10: Rewrite Airflow DAG

**Files:**
- Modify: `airflow/dags/reddit_trends_dag.py` → rename to `airflow/dags/startup_pulse_dag.py`

**Step 1: Delete old DAG and create new one**

```bash
rm airflow/dags/reddit_trends_dag.py
```

**Step 2: Write startup_pulse_dag.py**

New DAG with:
- `dag_id="startup_pulse_pipeline"`
- `schedule="0 8 * * *"` (daily at 8am UTC)
- 3 parallel extract tasks → clean → [extract_skills, market_metrics] → load
- Same default_args pattern (retries, backoff, timeout)

```python
# airflow/dags/startup_pulse_dag.py
"""Startup Pulse ETL pipeline DAG.

Scrapes startup job boards daily, cleans and analyzes postings
with NLP, and loads results into BigQuery.
"""

import pendulum
from airflow.models.dag import DAG
from airflow.operators.python import PythonOperator

default_args = {
    "owner": "startup-pulse",
    "retries": 2,
    "retry_delay": pendulum.duration(minutes=5),
    "retry_exponential_backoff": True,
    "execution_timeout": pendulum.duration(minutes=30),
}


def scrape_yc(**context):
    """Scrape YC Work at a Startup."""
    from src.extract.yc_scraper import YCScraper
    execution_date = context["ds"]
    output_dir = f"/opt/airflow/data/raw/yc/{execution_date}"
    result = YCScraper().scrape(output_dir)
    context["ti"].xcom_push(key="yc_metadata", value=result)
    return result


def scrape_wellfound(**context):
    """Scrape Wellfound job listings."""
    from src.extract.wellfound_scraper import WellfoundScraper
    execution_date = context["ds"]
    output_dir = f"/opt/airflow/data/raw/wellfound/{execution_date}"
    result = WellfoundScraper().scrape(output_dir)
    context["ti"].xcom_push(key="wellfound_metadata", value=result)
    return result


def scrape_hn(**context):
    """Scrape HN Who is Hiring thread."""
    from src.extract.hn_scraper import HNScraper
    execution_date = context["ds"]
    output_dir = f"/opt/airflow/data/raw/hn/{execution_date}"
    result = HNScraper().scrape(output_dir)
    context["ti"].xcom_push(key="hn_metadata", value=result)
    return result


def clean_and_normalize(**context):
    """Merge all scraped jobs and clean text fields."""
    import json
    import os
    from pathlib import Path
    from src.transform.text_cleaner import TextCleaner

    execution_date = context["ds"]
    all_jobs = []

    for source in ("yc", "wellfound", "hn"):
        path = f"/opt/airflow/data/raw/{source}/{execution_date}/jobs.json"
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as fh:
                all_jobs.extend(json.load(fh))

    cleaner = TextCleaner()
    cleaned = cleaner.clean_jobs(all_jobs)

    output_dir = f"/opt/airflow/data/cleaned/{execution_date}"
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    output_path = os.path.join(output_dir, "jobs.json")
    with open(output_path, "w", encoding="utf-8") as fh:
        json.dump(cleaned, fh, ensure_ascii=False, indent=2)

    context["ti"].xcom_push(key="clean_metadata", value={"total_jobs": len(cleaned)})
    return {"total_jobs": len(cleaned)}


def extract_skills(**context):
    """Extract skill trends from cleaned jobs."""
    import json
    import os
    from pathlib import Path
    from src.transform.skill_extractor import SkillExtractor

    execution_date = context["ds"]
    input_path = f"/opt/airflow/data/cleaned/{execution_date}/jobs.json"
    with open(input_path, "r", encoding="utf-8") as fh:
        jobs = json.load(fh)

    results = SkillExtractor().extract(jobs)

    output_dir = f"/opt/airflow/data/skills/{execution_date}"
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    output_path = os.path.join(output_dir, "skills.json")
    with open(output_path, "w", encoding="utf-8") as fh:
        json.dump(results, fh, ensure_ascii=False, indent=2)

    context["ti"].xcom_push(key="skills_metadata", value={"total_skills": len(results)})
    return {"total_skills": len(results)}


def aggregate_metrics(**context):
    """Aggregate market metrics from cleaned jobs."""
    import json
    import os
    from pathlib import Path
    from src.transform.metrics_aggregator import MetricsAggregator

    execution_date = context["ds"]
    input_path = f"/opt/airflow/data/cleaned/{execution_date}/jobs.json"
    with open(input_path, "r", encoding="utf-8") as fh:
        jobs = json.load(fh)

    results = MetricsAggregator().aggregate(jobs)

    output_dir = f"/opt/airflow/data/metrics/{execution_date}"
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    output_path = os.path.join(output_dir, "metrics.json")
    with open(output_path, "w", encoding="utf-8") as fh:
        json.dump(results, fh, ensure_ascii=False, indent=2)

    context["ti"].xcom_push(key="metrics_metadata", value={"sources": len(results)})
    return {"sources": len(results)}


def load_to_bigquery(**context):
    """Load all transformed data into BigQuery."""
    from src.load.bigquery_loader import BigQueryLoader
    execution_date = context["ds"]
    loader = BigQueryLoader()
    result = loader.load_all(
        cleaned_path=f"/opt/airflow/data/cleaned/{execution_date}/jobs.json",
        skills_path=f"/opt/airflow/data/skills/{execution_date}/skills.json",
        metrics_path=f"/opt/airflow/data/metrics/{execution_date}/metrics.json",
    )
    context["ti"].xcom_push(key="load_metadata", value=result)
    return result


with DAG(
    dag_id="startup_pulse_pipeline",
    default_args=default_args,
    description="Scrape startup job boards, extract skills with NLP, load to BigQuery",
    schedule="0 8 * * *",
    start_date=pendulum.datetime(2026, 3, 1, tz="UTC"),
    catchup=False,
    max_active_runs=1,
    tags=["jobs", "nlp", "bigquery", "etl", "startups"],
) as dag:

    scrape_yc_task = PythonOperator(task_id="scrape_yc", python_callable=scrape_yc)
    scrape_wellfound_task = PythonOperator(task_id="scrape_wellfound", python_callable=scrape_wellfound)
    scrape_hn_task = PythonOperator(task_id="scrape_hn", python_callable=scrape_hn)

    clean_task = PythonOperator(task_id="clean_and_normalize", python_callable=clean_and_normalize)

    skills_task = PythonOperator(task_id="extract_skills", python_callable=extract_skills)
    metrics_task = PythonOperator(task_id="aggregate_metrics", python_callable=aggregate_metrics)

    load_task = PythonOperator(task_id="load_to_bigquery", python_callable=load_to_bigquery)

    # 3 scrapers in parallel -> clean -> [skills, metrics] in parallel -> load
    [scrape_yc_task, scrape_wellfound_task, scrape_hn_task] >> clean_task
    clean_task >> [skills_task, metrics_task]
    [skills_task, metrics_task] >> load_task
```

**Step 3: Commit**

```bash
git rm airflow/dags/reddit_trends_dag.py
git add airflow/dags/startup_pulse_dag.py
git commit -m "Replace Reddit DAG with startup-pulse pipeline (3 scrapers, skill extraction)"
```

---

## Task 11: Rewrite Streamlit Dashboard

**Files:**
- Modify: `streamlit_app/app.py` (full rewrite for job market data)
- Keep: `streamlit_app/utils/bq_client.py` (unchanged)

**Step 1: Rewrite app.py**

4 pages: Overview, Skill Trends, Market Metrics, Job Explorer. Same pattern as current dashboard but queries the new tables (raw_jobs, skill_trends, market_metrics). Use `@st.cache_data(ttl=300)` for all queries.

Key queries:
- Overview: KPI cards from market_metrics + top skills from skill_trends
- Skill Trends: bar chart of skills by frequency, filterable by category, word cloud
- Market Metrics: salary distributions (box plots), remote %, jobs by company stage
- Job Explorer: filterable table from raw_jobs

**Step 2: Commit**

```bash
git add streamlit_app/app.py
git commit -m "Rebuild Streamlit dashboard for startup job market analytics"
```

---

## Task 12: Update Docker Compose Volumes and Makefile

**Files:**
- Modify: `docker-compose.yml` (add `./scripts` and `./airflow/data` volumes)
- Modify: `Makefile` (update init-bq command, add scrape-test target)

**Step 1: Add missing volumes to airflow containers**

In x-airflow-common volumes, add:
```yaml
    - ./scripts:/opt/airflow/scripts
    - ./airflow/data:/opt/airflow/data
```

**Step 2: Update Makefile**

```makefile
.PHONY: up down restart logs init-bq build

up:
	docker compose up -d

down:
	docker compose down

restart:
	docker compose down && docker compose up -d

logs:
	docker compose logs -f

init-bq:
	docker compose exec airflow-webserver python /opt/airflow/scripts/init_bigquery.py

build:
	docker compose build
```

**Step 3: Commit**

```bash
git add docker-compose.yml Makefile
git commit -m "Add missing Docker volumes and fix Makefile init-bq command"
```

---

## Task 13: Final Integration Test and Cleanup

**Step 1: Run all tests**

```bash
python -m pytest tests/ -v
```

Expected: All tests pass.

**Step 2: Verify Docker build**

```bash
docker compose build
```

**Step 3: Verify DAG syntax**

```bash
python -c "import ast; ast.parse(open('airflow/dags/startup_pulse_dag.py').read()); print('OK')"
```

**Step 4: Clean up __init__.py files if needed**

Ensure `tests/__init__.py` exists (it does).

**Step 5: Final commit**

```bash
git add -A
git commit -m "Integration cleanup: verify all tests pass and Docker builds"
```
