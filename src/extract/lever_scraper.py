# src/extract/lever_scraper.py
"""Lever Job Board API scraper.

Fetches jobs from multiple companies via Lever's public,
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

from src.utils.config import LEVER_API_BASE, LEVER_BOARD_TOKENS, SCRAPE_DELAY_SECONDS, is_software_role

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT = 30


class LeverScraper:
    """Scrapes job listings from Lever's public Postings API."""

    def scrape(self, output_dir: str) -> dict:
        """Fetch jobs from all configured Lever boards and save.

        Returns:
            Metadata dict with ``total_jobs`` and ``boards_scraped``.
        """
        all_jobs: list[dict] = []
        boards_scraped = 0

        for token in LEVER_BOARD_TOKENS:
            try:
                jobs = self._fetch_board(token)
                all_jobs.extend(jobs)
                boards_scraped += 1
                logger.info("Lever [%s]: %d jobs", token, len(jobs))
            except Exception as exc:
                logger.warning("Lever [%s] failed: %s", token, exc)

            time.sleep(SCRAPE_DELAY_SECONDS)

        Path(output_dir).mkdir(parents=True, exist_ok=True)
        output_path = os.path.join(output_dir, "jobs.json")
        with open(output_path, "w", encoding="utf-8") as fh:
            json.dump(all_jobs, fh, ensure_ascii=False, indent=2)

        logger.info(
            "Wrote %d Lever jobs from %d boards to %s",
            len(all_jobs), boards_scraped, output_path,
        )
        return {"total_jobs": len(all_jobs), "boards_scraped": boards_scraped}

    # -- Private helpers ------------------------------------------------------

    def _fetch_board(self, token: str) -> list[dict]:
        """Fetch and normalize all jobs from a single Lever board."""
        url = f"{LEVER_API_BASE}/{token}?mode=json"
        resp = requests.get(url, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()

        raw_jobs = resp.json()
        if not isinstance(raw_jobs, list):
            return []

        department = ""
        normalized = [self._normalize(raw, token, department) for raw in raw_jobs]
        filtered = [j for j in normalized if is_software_role(j["title"], j.get("_department", ""))]
        for j in filtered:
            j.pop("_department", None)
        return filtered

    def _normalize(self, raw: dict, board_token: str, _: str) -> dict:
        """Normalize a Lever API job into the shared schema."""
        lever_id = raw.get("id", "")
        title = raw.get("text", "")

        categories = raw.get("categories") or {}
        department = categories.get("department", "")
        location = categories.get("location", "")
        workplace_type = raw.get("workplaceType", "")

        description = raw.get("descriptionPlain", "")
        additional_plain = raw.get("additionalPlain", "")
        hosted_url = raw.get("hostedUrl", "")

        # Lever provides company name in the board token
        company = board_token.replace("-", " ").title()

        salary_min, salary_max = self._parse_salary(additional_plain)

        is_remote = workplace_type == "remote" or bool(
            re.search(r"\bremote\b", location, re.IGNORECASE)
        )

        id_str = f"{board_token}-{lever_id}"
        job_id = f"lv_{hashlib.md5(id_str.encode()).hexdigest()[:12]}"

        job = {
            "job_id": job_id,
            "source": "lever",
            "company": company,
            "title": title,
            "description": description,
            "salary_min": salary_min,
            "salary_max": salary_max,
            "currency": "USD" if salary_min else None,
            "location": location,
            "remote": is_remote,
            "company_stage": None,
            "yc_batch": None,
            "equity": None,
            "url": hosted_url,
            "collected_at": datetime.now(timezone.utc).isoformat(),
        }
        # Attach department for filtering (removed before output)
        job["_department"] = department
        return job

    @staticmethod
    def _parse_salary(text: str) -> tuple[int | None, int | None]:
        """Try to extract salary range from the additional/compensation text."""
        if not text:
            return None, None

        # Look for patterns like "$126,163 - $157,504" or "$180,000 - $250,000"
        amounts = re.findall(r"\$\s*([\d,]+)", text)
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
