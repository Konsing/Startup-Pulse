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
