# Reddit Trends Analysis Platform

An automated data pipeline that collects posts from popular subreddits, identifies trending topics using NLP, and visualizes engagement patterns through an interactive dashboard.

Built with Apache Airflow, Google BigQuery, and Streamlit.

## Architecture

```
Reddit API (PRAW)
       |
       v
+------------------+
|   Apache Airflow |     Every 6 hours (0 */6 * * *)
|   (Scheduler)    |
+--------+---------+
         |
         v
+--------+---------+     +-------------------+     +-----------------+
|    EXTRACT       | --> |    TRANSFORM      | --> |      LOAD       |
| Collect hot/top  |     | Clean text (NLTK) |     | Deduplicate     |
| posts from 9     |     | Extract keywords  |     | Validate        |
| subreddits       |     |   (TF-IDF)        |     | Append to       |
|                  |     | Aggregate metrics |     |   BigQuery      |
+------------------+     +-------------------+     +-----------------+
                                                          |
                                                          v
                                                   +-----------+
                                                   |  BigQuery  |
                                                   | 3 tables:  |
                                                   | raw_posts  |
                                                   | keyword_   |
                                                   |   trends   |
                                                   | subreddit_ |
                                                   |   metrics  |
                                                   +-----+-----+
                                                         |
                                                         v
                                                   +-----------+
                                                   | Streamlit  |
                                                   | Dashboard  |
                                                   +-----------+
```

## What It Tracks

| Category | Subreddits |
|----------|------------|
| Technology | r/technology, r/programming, r/artificial |
| Finance | r/wallstreetbets, r/stocks, r/CryptoCurrency |
| Gaming | r/gaming, r/pcgaming, r/Games |

The pipeline collects up to 100 posts per subreddit per run (50 hot + 50 top), yielding ~500-700 unique posts every 6 hours after deduplication.

## Tech Stack

| Component | Technology | Purpose |
|-----------|-----------|---------|
| Orchestration | Apache Airflow 2.11.0 | Schedule and monitor ETL pipeline |
| Data Warehouse | Google BigQuery | Store and query structured data |
| Visualization | Streamlit | Interactive analytics dashboard |
| Data Collection | PRAW (Python Reddit API Wrapper) | Fetch posts from Reddit |
| NLP | NLTK + scikit-learn TF-IDF | Text cleaning and keyword extraction |
| Infrastructure | Docker Compose | Container orchestration |
| Database | PostgreSQL 15 | Airflow metadata storage |

## ETL Pipeline

The Airflow DAG (`reddit_trends_pipeline`) runs every 6 hours and executes 5 tasks:

```
extract_reddit_posts
        |
        v
transform_clean_text
       / \
      v   v
extract   aggregate
keywords  metrics
      \   /
       v v
load_to_bigquery
```

### Extract
- Connects to Reddit via OAuth script credentials (PRAW)
- Fetches `hot` and `top` listings from each subreddit
- Retry logic with exponential backoff on API errors
- One subreddit failure does not block the pipeline

### Transform
Three parallel-capable processing steps:

1. **Text Cleaning** (NLTK): Lowercase, remove URLs/markdown/special characters, tokenize, remove stop words (English + Reddit-specific), lemmatize
2. **Keyword Extraction** (TF-IDF): Groups posts by subreddit, fits `TfidfVectorizer(ngram_range=(1,2))`, ranks keywords by average TF-IDF score, computes engagement correlation
3. **Metrics Aggregation** (pandas): Calculates per-subreddit statistics — average score, median score, comment counts, upvote ratios, posting rate

### Load
- Deduplicates within each run (hot+top overlap) and across runs (query existing post_ids)
- Validates data (null checks, text truncation, type enforcement)
- Appends to BigQuery tables with retry logic on transient errors

## BigQuery Schema

Three tables, all partitioned by `collected_at` (DAY):

**`raw_posts`** — Every collected post with original and cleaned text
- Clustered by `subreddit, category`
- Key columns: `post_id`, `title`, `score`, `num_comments`, `cleaned_title`, `cleaned_selftext`

**`keyword_trends`** — TF-IDF keyword rankings per collection window
- Clustered by `category, subreddit`
- Key columns: `keyword`, `tfidf_score`, `frequency`, `avg_score`, `avg_comments`

**`subreddit_metrics`** — Aggregated engagement stats per subreddit
- Clustered by `category`
- Key columns: `avg_score`, `median_score`, `total_comments`, `posting_rate_per_hour`

## Dashboard

The Streamlit dashboard (port 8501) has four views:

**Overview** — KPI cards (subreddits tracked, total posts, avg score, unique keywords) with top keywords and subreddits tables

**Keyword Trends** — Horizontal bar chart of top keywords by TF-IDF score, word cloud visualization, category filter, detailed keyword table

**Subreddit Metrics** — Bar chart of average scores, scatter plot of score vs. comments, metrics over time with subreddit selector

**Recent Posts** — Filterable/sortable table of collected posts with category and subreddit dropdowns

## Project Structure

```
reddit-trends/
├── docker-compose.yml          # 5 services: postgres, airflow-init, webserver, scheduler, streamlit
├── Makefile                    # make up/down/restart/logs/build/init-bq
├── .env.example                # Template for environment variables
│
├── airflow/
│   ├── Dockerfile              # apache/airflow:2.11.0 + Python dependencies
│   ├── requirements.txt        # praw, google-cloud-bigquery, nltk, scikit-learn, pandas
│   └── dags/
│       └── reddit_trends_dag.py
│
├── src/
│   ├── extract/
│   │   └── reddit_collector.py     # PRAW-based post collection with retries
│   ├── transform/
│   │   ├── text_cleaner.py         # NLTK text preprocessing pipeline
│   │   ├── keyword_extractor.py    # TF-IDF keyword ranking
│   │   └── metrics_aggregator.py   # Engagement statistics
│   ├── load/
│   │   └── bigquery_loader.py      # BigQuery insertion with deduplication
│   └── utils/
│       ├── config.py               # Centralized configuration
│       └── deduplication.py        # In-run and cross-run dedup logic
│
├── streamlit_app/
│   ├── Dockerfile              # python:3.11-slim + streamlit + plotly
│   ├── requirements.txt
│   ├── app.py                  # Dashboard with 4 views
│   └── utils/
│       └── bq_client.py        # Cached BigQuery client
│
├── scripts/
│   └── init_bigquery.py        # One-time dataset and table creation
│
└── credentials/                # GCP service account key (gitignored)
    └── .gitkeep
```

## Quick Start

```bash
# 1. Clone and configure
cp .env.example .env
# Edit .env with your Reddit API and GCP credentials

# 2. Place GCP service account key
cp /path/to/your/service-account.json credentials/service-account.json

# 3. Build and start
make build
make up

# 4. Initialize BigQuery tables
make init-bq

# 5. Access the services
# Airflow UI: http://localhost:8080 (admin/admin)
# Streamlit:  http://localhost:8501
```

See [SETUP_GUIDE.md](SETUP_GUIDE.md) for detailed step-by-step instructions including Reddit API and GCP setup.

## Free-Tier Budget

| Resource | Free Tier Limit | Estimated Usage | Headroom |
|----------|----------------|-----------------|----------|
| BigQuery Storage | 10 GB/month | ~140 MB/month | 98.6% free |
| BigQuery Queries | 1 TB/month | ~3 GB/month | 99.7% free |
| Reddit API | 60 req/min | ~18 req/run (72/day) | Well within limits |

## Configuration

All pipeline settings are centralized in `src/utils/config.py`:

```python
SUBREDDIT_CONFIG = {
    "technology": ["technology", "programming", "artificial"],
    "finance": ["wallstreetbets", "stocks", "CryptoCurrency"],
    "gaming": ["gaming", "pcgaming", "Games"],
}

POSTS_PER_LISTING = 50      # Posts per listing type (hot/top)
TOP_TIME_FILTER = "day"     # Time filter for top posts
API_SLEEP_SECONDS = 1       # Delay between API calls

# NLP settings
TFIDF_MAX_FEATURES = 200
TFIDF_NGRAM_RANGE = (1, 2)  # Unigrams and bigrams
TFIDF_MIN_DF = 2            # Min document frequency
TFIDF_MAX_DF = 0.85         # Max document frequency
MAX_KEYWORDS_PER_SUBREDDIT = 30
```

To add a new subreddit, simply add it to the appropriate category list in `SUBREDDIT_CONFIG`.

## How It Works

### Keyword Extraction

The system uses TF-IDF (Term Frequency-Inverse Document Frequency) to identify trending topics without any paid AI APIs:

1. Post titles and body text are cleaned: lowercased, URLs stripped, stop words removed, lemmatized
2. A `TfidfVectorizer` fits on all documents within each subreddit, producing unigrams and bigrams
3. Keywords are ranked by average TF-IDF score — this naturally surfaces terms that are frequent within a subreddit but distinctive (not appearing in every post)
4. Each keyword is enriched with engagement metrics: average post score and comment count of posts containing that keyword

### Deduplication

Posts are deduplicated at two levels:
- **Within each run**: A post appearing in both `hot` and `top` listings is kept once with `listing_type="hot+top"`
- **Across runs**: Before loading to BigQuery, existing `post_id` values from the last 24 hours are queried and filtered out

### Error Resilience

- Reddit API failures for individual subreddits are caught and logged — the pipeline continues with remaining subreddits
- Airflow retries each task up to 2 times with exponential backoff
- BigQuery load retries on `ServiceUnavailable` errors
- Missing BigQuery tables are auto-created on first load attempt
