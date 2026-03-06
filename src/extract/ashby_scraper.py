# src/extract/ashby_scraper.py
"""Ashby ATS job board scraper.

Fetches jobs from multiple companies via Ashby's public
posting API. No authentication required.
"""

import hashlib
import json
import logging
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

from src.utils.config import ASHBY_API_BASE, ASHBY_BOARD_TOKENS, SCRAPE_DELAY_SECONDS, is_software_role

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT = 30


class AshbyScraper:
    """Scrapes job listings from Ashby's public posting API."""

    def scrape(self, output_dir: str) -> dict:
        """Fetch jobs from all configured Ashby boards and save.

        Returns:
            Metadata dict with ``total_jobs`` and ``boards_scraped``.
        """
        all_jobs: list[dict] = []
        boards_scraped = 0

        for token in ASHBY_BOARD_TOKENS:
            try:
                jobs = self._fetch_board(token)
                all_jobs.extend(jobs)
                boards_scraped += 1
                logger.info("Ashby [%s]: %d software jobs", token, len(jobs))
            except Exception as exc:
                logger.warning("Ashby [%s] failed: %s", token, exc)

            time.sleep(SCRAPE_DELAY_SECONDS)

        Path(output_dir).mkdir(parents=True, exist_ok=True)
        output_path = os.path.join(output_dir, "jobs.json")
        with open(output_path, "w", encoding="utf-8") as fh:
            json.dump(all_jobs, fh, ensure_ascii=False, indent=2)

        logger.info(
            "Wrote %d Ashby jobs from %d boards to %s",
            len(all_jobs), boards_scraped, output_path,
        )
        return {"total_jobs": len(all_jobs), "boards_scraped": boards_scraped}

    # -- Private helpers ------------------------------------------------------

    def _fetch_board(self, token: str) -> list[dict]:
        """Fetch and normalize software jobs from a single Ashby board."""
        url = f"{ASHBY_API_BASE}/{token}"
        resp = requests.get(url, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()

        data = resp.json()
        raw_jobs = data.get("jobs", [])
        normalized = [self._normalize(raw, token) for raw in raw_jobs]
        return [j for j in normalized if is_software_role(j["title"])]

    def _normalize(self, raw: dict, board_token: str) -> dict:
        """Normalize an Ashby API job into the shared schema."""
        ashby_id = raw.get("id", "")
        title = raw.get("title", "")

        location = raw.get("location", "")
        is_remote = raw.get("isRemote", False)
        if is_remote and "remote" not in location.lower():
            location = f"{location} (Remote)" if location else "Remote"

        description_html = raw.get("descriptionHtml", "")
        description = self._strip_html(description_html) if description_html else (raw.get("descriptionPlain", ""))

        job_url = raw.get("jobUrl", "")

        id_str = f"{board_token}-{ashby_id}"
        job_id = f"ab_{hashlib.md5(id_str.encode()).hexdigest()[:12]}"

        return {
            "job_id": job_id,
            "source": "ashby",
            "company": board_token.replace("-", " ").title(),
            "title": title,
            "description": description,
            "salary_min": None,
            "salary_max": None,
            "currency": None,
            "location": location,
            "remote": is_remote or bool(re.search(r"\bremote\b", location, re.IGNORECASE)),
            "company_stage": None,
            "yc_batch": None,
            "equity": None,
            "url": job_url,
            "collected_at": datetime.now(timezone.utc).isoformat(),
        }

    @staticmethod
    def _strip_html(html: str) -> str:
        """Remove HTML tags, collapse whitespace."""
        text = re.sub(r"<[^>]+>", " ", html)
        text = re.sub(r"&[a-zA-Z]+;", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text
