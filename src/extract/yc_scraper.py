# src/extract/yc_scraper.py
"""Work at a Startup (YC) job scraper using Playwright.

Navigates the JS-rendered job listing pages across all role categories,
extracts job cards, and normalizes them into the shared job schema.
"""

import hashlib
import json
import logging
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path

from src.utils.config import (
    YC_JOBS_BASE_URL,
    YC_CATEGORY_SLUGS,
    SCRAPE_DELAY_SECONDS,
    SCRAPE_TIMEOUT_MS,
)

logger = logging.getLogger(__name__)


class YCScraper:
    """Scrapes job listings from workatastartup.com across all role categories."""

    def scrape(self, output_dir: str) -> dict:
        """Launch a headless browser, visit each role category page, and save.

        Returns:
            Metadata dict with ``total_jobs``.
        """
        from playwright.sync_api import sync_playwright

        seen_urls: set[str] = set()
        raw_jobs: list[dict] = []

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.set_default_timeout(SCRAPE_TIMEOUT_MS)

            for slug in YC_CATEGORY_SLUGS:
                url = f"{YC_JOBS_BASE_URL}/{slug}"
                page.goto(url)
                page.wait_for_load_state("networkidle")

                cards = self._extract_cards(page)
                # Deduplicate across categories (same job can appear in multiple)
                new_cards = [c for c in cards if c.get("url") not in seen_urls]
                seen_urls.update(c.get("url", "") for c in new_cards)
                raw_jobs.extend(new_cards)

                logger.info("YC scrape [%s]: %d jobs (%d new)", slug, len(cards), len(new_cards))
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
        """Extract job card data from the current page DOM.

        Each job on workatastartup.com is represented by a ``.job-name``
        div containing an ``<a>`` with the title and URL.  Company info
        lives in the ancestor card (the ``.bg-beige-lighter`` div) under
        ``.company-details .font-bold``.  Job metadata (type, location,
        category) lives in the sibling ``.job-details`` paragraph.
        """
        cards = []
        job_name_elements = page.query_selector_all(".job-name")

        for el in job_name_elements:
            try:
                info = el.evaluate("""el => {
                    const a = el.querySelector('a');
                    const title = a ? a.innerText.trim() : '';
                    const url = a ? a.getAttribute('href') : '';

                    let card = el;
                    for (let i = 0; i < 10; i++) {
                        card = card.parentElement;
                        if (!card) break;
                        if (card.className && card.className.includes('bg-beige-lighter')) break;
                    }

                    let company = '';
                    if (card) {
                        const bold = card.querySelector('.company-details .font-bold');
                        if (bold) company = bold.innerText.trim();
                    }

                    const parent = el.parentElement;
                    const details = parent ? parent.querySelector('.job-details') : null;
                    const spans = details
                        ? Array.from(details.querySelectorAll('span')).map(s => s.innerText.trim())
                        : [];

                    const description = card ? card.innerText.trim() : '';

                    return {title, url, company, spans, description};
                }""")

                if not info.get("title") or not info.get("company"):
                    continue

                spans = info.get("spans", [])
                location = spans[1] if len(spans) > 1 else ""

                batch_match = re.search(r"\(([WSF]\d{2})\)", info.get("company", ""))
                batch = batch_match.group(1) if batch_match else ""

                company = re.sub(r"\s*\([WSF]\d{2}\)\s*", "", info["company"]).replace("\xa0", " ").strip()

                cards.append({
                    "title": info["title"],
                    "company": company,
                    "location": location,
                    "salary": "",
                    "description": info.get("description", ""),
                    "url": info.get("url", ""),
                    "batch": batch,
                })
            except Exception as exc:
                logger.debug("Failed to parse YC card: %s", exc)
                continue

        return cards

    def _normalize(self, raw: dict) -> dict:
        """Normalize a raw scraped job into the shared schema."""
        salary_min, salary_max = self._parse_salary(raw.get("salary", ""))

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
