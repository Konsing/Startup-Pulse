"""Centralized configuration for the Reddit Trends pipeline."""

# ── Subreddit configuration ──────────────────────────────────────────
# Each category maps to a list of subreddit names to collect from.
SUBREDDIT_CONFIG = {
    "technology": ["technology", "programming", "artificial"],
    "finance": ["wallstreetbets", "stocks", "CryptoCurrency"],
    "gaming": ["gaming", "pcgaming", "Games"],
}

# ── Reddit collection settings ───────────────────────────────────────
POSTS_PER_LISTING = 50          # Posts to fetch per listing type (hot/top)
TOP_TIME_FILTER = "day"         # Time filter for subreddit.top()
API_SLEEP_SECONDS = 1           # Delay between API calls

# ── NLP settings (used by Phase 3) ──────────────────────────────────
TFIDF_MAX_FEATURES = 200
TFIDF_NGRAM_RANGE = (1, 2)
TFIDF_MIN_DF = 2
TFIDF_MAX_DF = 0.85
MAX_KEYWORDS_PER_SUBREDDIT = 30

# ── BigQuery settings (used by Phase 4) ─────────────────────────────
BQ_LOCATION = "US"
