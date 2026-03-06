# src/transform/text_cleaner.py
"""Text cleaning and preprocessing for job descriptions.

Downloads required NLTK data, removes noise (HTML, URLs, special
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

JOB_STOP_WORDS = {
    "amp", "nbsp", "http", "https", "www", "com", "org",
    "apply", "click", "email", "send", "resume", "cover", "letter",
    "please", "position", "candidate", "applicant", "role",
    "company", "team", "join", "work", "working",
    "just", "like", "also", "would", "one", "get", "got",
    "even", "much", "thing", "really", "well",
}


class TextCleaner:
    """Clean and normalize job posting text for downstream NLP tasks."""

    def __init__(self) -> None:
        nltk.download("stopwords", quiet=True)
        nltk.download("punkt", quiet=True)
        nltk.download("punkt_tab", quiet=True)
        nltk.download("wordnet", quiet=True)

        self.stop_words = set(stopwords.words("english")) | JOB_STOP_WORDS
        self.lemmatizer = WordNetLemmatizer()
        logger.info("TextCleaner initialized with %d stop words", len(self.stop_words))

    def clean_text(self, text: str) -> str:
        """Clean a single text string through the full NLP pipeline."""
        if not text:
            return ""

        text = text.lower()
        text = re.sub(r"<[^>]+>", " ", text)              # Remove HTML tags
        text = re.sub(r"https?://\S+", "", text)           # Remove URLs
        text = re.sub(r"www\.\S+", "", text)
        text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)  # Markdown links
        text = re.sub(r"[^a-zA-Z0-9+#.\s]", "", text)     # Keep +, #, . for C++, C#, etc.
        text = re.sub(r"\s+", " ", text).strip()

        tokens = word_tokenize(text)
        tokens = [t for t in tokens if t not in self.stop_words and len(t) > 1]
        tokens = [self.lemmatizer.lemmatize(t) for t in tokens]

        return " ".join(tokens)

    def clean_jobs(self, jobs: list[dict]) -> list[dict]:
        """Clean description fields on a list of job dicts.

        Adds ``cleaned_description`` to each job dict. Returns the
        modified list (mutates in place).
        """
        for job in jobs:
            job["cleaned_description"] = self.clean_text(job.get("description", ""))

        jobs_with_content = sum(1 for j in jobs if j["cleaned_description"])
        logger.info("Cleaned %d jobs (%d with content)", len(jobs), jobs_with_content)
        return jobs
