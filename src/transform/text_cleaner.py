"""Text cleaning and preprocessing for Reddit posts.

Downloads required NLTK data, removes noise (URLs, markdown, special
characters), tokenizes, removes stop words, and lemmatizes.
"""

import json
import logging
import re
from pathlib import Path

import nltk
from nltk.corpus import stopwords
from nltk.stem import WordNetLemmatizer
from nltk.tokenize import word_tokenize

logger = logging.getLogger(__name__)

REDDIT_STOP_WORDS = {
    "reddit", "subreddit", "post", "comment", "upvote", "downvote",
    "edit", "update", "deleted", "removed", "amp", "nbsp",
    "http", "https", "www", "com", "org",
    "just", "like", "think", "know", "really", "people", "would",
    "one", "get", "got", "also", "even", "much", "thing",
}


class TextCleaner:
    """Clean and normalize Reddit post text for downstream NLP tasks."""

    def __init__(self) -> None:
        nltk.download("stopwords", quiet=True)
        nltk.download("punkt", quiet=True)
        nltk.download("punkt_tab", quiet=True)
        nltk.download("wordnet", quiet=True)

        self.stop_words = set(stopwords.words("english")) | REDDIT_STOP_WORDS
        self.lemmatizer = WordNetLemmatizer()
        logger.info("TextCleaner initialized with %d stop words", len(self.stop_words))

    # ── public API ────────────────────────────────────────────────────

    def clean_text(self, text: str) -> str:
        """Clean a single text string through the full NLP pipeline.

        Steps: lowercase -> remove URLs -> remove markdown links -> remove
        special characters -> collapse whitespace -> tokenize -> remove
        stop words & short tokens -> lemmatize -> rejoin.
        """
        if not text:
            return ""

        # Lowercase
        text = text.lower()

        # Remove URLs (http/https/www patterns)
        text = re.sub(r"https?://\S+", "", text)
        text = re.sub(r"www\.\S+", "", text)

        # Remove markdown links [text](url)
        text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)

        # Remove special characters (keep alphanumeric + spaces)
        text = re.sub(r"[^a-zA-Z0-9\s]", "", text)

        # Collapse whitespace
        text = re.sub(r"\s+", " ", text).strip()

        # Tokenize
        tokens = word_tokenize(text)

        # Remove stop words and tokens with length <= 2
        tokens = [t for t in tokens if t not in self.stop_words and len(t) > 2]

        # Lemmatize
        tokens = [self.lemmatizer.lemmatize(t) for t in tokens]

        return " ".join(tokens)

    def clean_posts(self, input_path: str, output_path: str) -> dict:
        """Read raw posts JSON, clean text fields, and write cleaned posts.

        Args:
            input_path: Path to the raw ``posts.json`` file.
            output_path: Path where cleaned posts JSON will be written.

        Returns:
            Metadata dict with ``total_posts`` and ``posts_with_content``.
        """
        logger.info("Reading raw posts from %s", input_path)
        with open(input_path, "r", encoding="utf-8") as fh:
            posts = json.load(fh)

        posts_with_content = 0

        for post in posts:
            post["cleaned_title"] = self.clean_text(post.get("title", ""))
            post["cleaned_selftext"] = self.clean_text(post.get("selftext", ""))

            if post["cleaned_title"] or post["cleaned_selftext"]:
                posts_with_content += 1

        # Write cleaned posts
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as fh:
            json.dump(posts, fh, ensure_ascii=False, indent=2)

        metadata = {
            "total_posts": len(posts),
            "posts_with_content": posts_with_content,
        }
        logger.info(
            "Cleaned %d posts (%d with content) -> %s",
            metadata["total_posts"],
            metadata["posts_with_content"],
            output_path,
        )
        return metadata
