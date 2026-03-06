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
