# src/extract/greenhouse_scraper.py
"""Greenhouse Job Board API scraper.

Fetches jobs from multiple companies via Greenhouse's public,
unauthenticated JSON API. No browser or Playwright needed.
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

from src.utils.config import GREENHOUSE_API_BASE, GREENHOUSE_BOARD_TOKENS, SCRAPE_DELAY_SECONDS, is_software_role

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT = 30


class GreenhouseScraper:
    """Scrapes job listings from Greenhouse's public Job Board API."""

    def scrape(self, output_dir: str) -> dict:
        """Fetch jobs from all configured Greenhouse boards and save.

        Returns:
            Metadata dict with ``total_jobs`` and ``boards_scraped``.
        """
        all_jobs: list[dict] = []
        boards_scraped = 0

        for token in GREENHOUSE_BOARD_TOKENS:
            try:
                jobs = self._fetch_board(token)
                all_jobs.extend(jobs)
                boards_scraped += 1
                logger.info("Greenhouse [%s]: %d jobs", token, len(jobs))
            except Exception as exc:
                logger.warning("Greenhouse [%s] failed: %s", token, exc)

            time.sleep(SCRAPE_DELAY_SECONDS)

        Path(output_dir).mkdir(parents=True, exist_ok=True)
        output_path = os.path.join(output_dir, "jobs.json")
        with open(output_path, "w", encoding="utf-8") as fh:
            json.dump(all_jobs, fh, ensure_ascii=False, indent=2)

        logger.info(
            "Wrote %d Greenhouse jobs from %d boards to %s",
            len(all_jobs), boards_scraped, output_path,
        )
        return {"total_jobs": len(all_jobs), "boards_scraped": boards_scraped}

    # -- Private helpers ------------------------------------------------------

    def _fetch_board(self, token: str) -> list[dict]:
        """Fetch and normalize all jobs from a single Greenhouse board."""
        url = f"{GREENHOUSE_API_BASE}/{token}/jobs?content=true"
        resp = requests.get(url, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()

        data = resp.json()
        raw_jobs = data.get("jobs", [])
        normalized = [self._normalize(raw, token) for raw in raw_jobs]
        return [j for j in normalized if is_software_role(j["title"])]

    def _normalize(self, raw: dict, board_token: str) -> dict:
        """Normalize a Greenhouse API job into the shared schema."""
        gh_id = raw.get("id", "")
        title = raw.get("title", "")
        company = raw.get("company_name", board_token)

        location_obj = raw.get("location") or {}
        location = location_obj.get("name", "")

        description = self._strip_html(raw.get("content", ""))
        absolute_url = raw.get("absolute_url", "")

        salary_min, salary_max = self._parse_salary_from_metadata(raw.get("metadata"))

        departments = [d.get("name", "") for d in (raw.get("departments") or [])]

        id_str = f"{board_token}-{gh_id}"
        job_id = f"gh_{hashlib.md5(id_str.encode()).hexdigest()[:12]}"

        return {
            "job_id": job_id,
            "source": "greenhouse",
            "company": company,
            "title": title,
            "description": description,
            "salary_min": salary_min,
            "salary_max": salary_max,
            "currency": "USD" if salary_min else None,
            "location": location,
            "remote": bool(re.search(r"\bremote\b", location, re.IGNORECASE)),
            "company_stage": None,
            "yc_batch": None,
            "equity": None,
            "url": absolute_url,
            "collected_at": datetime.now(timezone.utc).isoformat(),
        }

    @staticmethod
    def _strip_html(html: str) -> str:
        """Remove HTML tags, collapse whitespace."""
        text = re.sub(r"<[^>]+>", " ", html)
        text = re.sub(r"&[a-zA-Z]+;", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text

    @staticmethod
    def _parse_salary_from_metadata(metadata: list | None) -> tuple[int | None, int | None]:
        """Try to extract salary from Greenhouse metadata fields."""
        if not metadata:
            return None, None

        for field in metadata:
            name = (field.get("name") or "").lower()
            value = str(field.get("value") or "")
            if any(kw in name for kw in ("salary", "compensation", "pay")):
                amounts = re.findall(r"\d[\d,]*", value)
                parsed = []
                for amt in amounts:
                    num = int(amt.replace(",", ""))
                    if 10_000 <= num <= 1_000_000:
                        parsed.append(num)
                if len(parsed) >= 2:
                    return min(parsed), max(parsed)
                if len(parsed) == 1:
                    return parsed[0], parsed[0]

        return None, None
