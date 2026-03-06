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
