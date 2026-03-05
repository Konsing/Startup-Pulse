"""Keyword extraction using TF-IDF per subreddit/category group.

Groups cleaned posts by (subreddit, category), fits a TF-IDF vectorizer
on each group, and selects the top keywords ranked by average TF-IDF score.
"""

import json
import logging
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer

from src.utils.config import (
    MAX_KEYWORDS_PER_SUBREDDIT,
    TFIDF_MAX_DF,
    TFIDF_MAX_FEATURES,
    TFIDF_MIN_DF,
    TFIDF_NGRAM_RANGE,
)

logger = logging.getLogger(__name__)


class KeywordExtractor:
    """Extract top keywords per subreddit/category using TF-IDF."""

    def extract_keywords(self, input_path: str, output_path: str) -> dict:
        """Read cleaned posts, compute TF-IDF keywords, and write results.

        Args:
            input_path: Path to the cleaned ``posts.json`` file.
            output_path: Path where ``keywords.json`` will be written.

        Returns:
            Metadata dict with ``total_keywords`` and
            ``subreddits_processed``.
        """
        logger.info("Reading cleaned posts from %s", input_path)
        with open(input_path, "r", encoding="utf-8") as fh:
            posts = json.load(fh)

        df = pd.DataFrame(posts)
        all_keywords: list[dict] = []
        subreddits_processed = 0

        for (subreddit, category), group_df in df.groupby(["subreddit", "category"]):
            # Build combined text per post
            documents = (
                group_df["cleaned_title"].fillna("")
                + " "
                + group_df["cleaned_selftext"].fillna("")
            ).str.strip().tolist()

            # Skip groups with fewer than 2 documents
            if len(documents) < 2:
                logger.debug(
                    "Skipping r/%s (%s) — only %d document(s)",
                    subreddit, category, len(documents),
                )
                continue

            try:
                vectorizer = TfidfVectorizer(
                    max_features=TFIDF_MAX_FEATURES,
                    ngram_range=TFIDF_NGRAM_RANGE,
                    min_df=TFIDF_MIN_DF,
                    max_df=TFIDF_MAX_DF,
                )
                tfidf_matrix = vectorizer.fit_transform(documents)
            except ValueError as exc:
                logger.warning(
                    "TF-IDF failed for r/%s (%s): %s", subreddit, category, exc
                )
                continue

            feature_names = vectorizer.get_feature_names_out()
            avg_scores = np.asarray(tfidf_matrix.mean(axis=0)).flatten()

            # Rank by average TF-IDF score, take top N
            top_indices = avg_scores.argsort()[::-1][:MAX_KEYWORDS_PER_SUBREDDIT]

            for idx in top_indices:
                keyword = feature_names[idx]
                tfidf_score = float(avg_scores[idx])

                # Count of documents containing this keyword
                col = tfidf_matrix[:, idx].toarray().flatten()
                frequency = int((col > 0).sum())

                # Compute average score/comments for posts containing keyword
                mask = col > 0
                matching_posts = group_df.iloc[np.where(mask)[0]]
                avg_post_score = float(matching_posts["score"].mean()) if len(matching_posts) > 0 else 0.0
                avg_comments = float(matching_posts["num_comments"].mean()) if len(matching_posts) > 0 else 0.0

                all_keywords.append({
                    "keyword": keyword,
                    "subreddit": subreddit,
                    "category": category,
                    "frequency": frequency,
                    "tfidf_score": tfidf_score,
                    "num_posts": len(documents),
                    "avg_score": avg_post_score,
                    "avg_comments": avg_comments,
                })

            subreddits_processed += 1
            logger.info(
                "Extracted %d keywords from r/%s (%s)",
                min(len(top_indices), MAX_KEYWORDS_PER_SUBREDDIT),
                subreddit,
                category,
            )

        # Write results
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as fh:
            json.dump(all_keywords, fh, ensure_ascii=False, indent=2)

        metadata = {
            "total_keywords": len(all_keywords),
            "subreddits_processed": subreddits_processed,
        }
        logger.info(
            "Wrote %d keywords across %d subreddits -> %s",
            metadata["total_keywords"],
            metadata["subreddits_processed"],
            output_path,
        )
        return metadata
