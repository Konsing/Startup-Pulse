"""Reddit data collector using PRAW.

Iterates over configured subreddits, fetches hot and top posts,
serializes them to dicts, and writes the results as JSON.
"""

import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import praw
import praw.exceptions
import prawcore.exceptions

from src.utils.config import (
    API_SLEEP_SECONDS,
    POSTS_PER_LISTING,
    SUBREDDIT_CONFIG,
    TOP_TIME_FILTER,
)

logger = logging.getLogger(__name__)

# Retry configuration
_MAX_RETRIES = 3
_BACKOFF_SECONDS = [5, 15, 30]


class RedditCollector:
    """Collects posts from Reddit using the PRAW library."""

    def __init__(self) -> None:
        self.reddit = praw.Reddit(
            client_id=os.environ["REDDIT_CLIENT_ID"],
            client_secret=os.environ["REDDIT_CLIENT_SECRET"],
            user_agent=os.environ["REDDIT_USER_AGENT"],
        )
        logger.info("PRAW Reddit instance created (read-only=%s)", self.reddit.read_only)

    # ── public API ───────────────────────────────────────────────────

    def collect_posts(self, output_dir: str) -> dict:
        """Collect posts from all configured subreddits and write to JSON.

        Args:
            output_dir: Directory where ``posts.json`` will be written.

        Returns:
            Metadata dict with keys ``total_posts``, ``subreddits_collected``,
            and ``errors``.
        """
        all_posts: list[dict] = []
        subreddits_collected: list[str] = []
        errors: list[str] = []

        for category, subreddit_names in SUBREDDIT_CONFIG.items():
            for sub_name in subreddit_names:
                logger.info("Collecting from r/%s (category=%s)", sub_name, category)
                try:
                    posts = self._collect_subreddit(sub_name, category)
                    all_posts.extend(posts)
                    subreddits_collected.append(sub_name)
                    logger.info(
                        "Collected %d posts from r/%s", len(posts), sub_name
                    )
                except Exception as exc:
                    msg = f"Failed to collect r/{sub_name}: {exc}"
                    logger.warning(msg)
                    errors.append(msg)

        # Persist to disk
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        output_path = os.path.join(output_dir, "posts.json")
        with open(output_path, "w", encoding="utf-8") as fh:
            json.dump(all_posts, fh, ensure_ascii=False, indent=2)
        logger.info("Wrote %d posts to %s", len(all_posts), output_path)

        result = {
            "total_posts": len(all_posts),
            "subreddits_collected": subreddits_collected,
            "errors": errors,
        }
        return result

    # ── private helpers ──────────────────────────────────────────────

    def _collect_subreddit(self, sub_name: str, category: str) -> list[dict]:
        """Collect hot and top posts from a single subreddit with retry logic."""
        posts: list[dict] = []

        subreddit = self._fetch_with_retry(lambda: self.reddit.subreddit(sub_name))

        # Hot posts
        hot_submissions = self._fetch_with_retry(
            lambda: list(subreddit.hot(limit=POSTS_PER_LISTING))
        )
        for submission in hot_submissions:
            posts.append(self._serialize(submission, category, "hot"))
        time.sleep(API_SLEEP_SECONDS)

        # Top posts
        top_submissions = self._fetch_with_retry(
            lambda: list(subreddit.top(time_filter=TOP_TIME_FILTER, limit=POSTS_PER_LISTING))
        )
        for submission in top_submissions:
            posts.append(self._serialize(submission, category, "top"))
        time.sleep(API_SLEEP_SECONDS)

        return posts

    def _fetch_with_retry(self, func):
        """Execute *func* with up to ``_MAX_RETRIES`` attempts on transient errors."""
        for attempt in range(_MAX_RETRIES):
            try:
                return func()
            except (
                praw.exceptions.RedditAPIException,
                prawcore.exceptions.ResponseException,
            ) as exc:
                if attempt < _MAX_RETRIES - 1:
                    wait = _BACKOFF_SECONDS[attempt]
                    logger.warning(
                        "Retry %d/%d after %ds — %s",
                        attempt + 1,
                        _MAX_RETRIES,
                        wait,
                        exc,
                    )
                    time.sleep(wait)
                else:
                    raise

    @staticmethod
    def _serialize(submission, category: str, listing_type: str) -> dict:
        """Convert a PRAW Submission object to a plain dict."""
        author_name = "[deleted]"
        if submission.author is not None:
            author_name = str(submission.author)

        return {
            "post_id": f"t3_{submission.id}",
            "subreddit": str(submission.subreddit),
            "category": category,
            "title": submission.title,
            "selftext": submission.selftext or "",
            "author": author_name,
            "score": int(submission.score),
            "upvote_ratio": float(submission.upvote_ratio),
            "num_comments": int(submission.num_comments),
            "url": submission.url,
            "permalink": f"https://www.reddit.com{submission.permalink}",
            "is_self": bool(submission.is_self),
            "created_utc": datetime.fromtimestamp(
                submission.created_utc, tz=timezone.utc
            ).isoformat(),
            "collected_at": datetime.now(timezone.utc).isoformat(),
            "flair": submission.link_flair_text or "",
            "listing_type": listing_type,
        }
