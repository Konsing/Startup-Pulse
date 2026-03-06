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
