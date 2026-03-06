# Startup Pulse — Job Market Intelligence Platform

An automated data pipeline that scrapes startup job postings from YC, Wellfound, and Hacker News, extracts trending skills using NLP, and visualizes market signals through an interactive dashboard.

Built with Apache Airflow, Google BigQuery, and Streamlit.

## Architecture

```
Job Board Scrapers
  (Playwright + HN API)
       |
       v
+------------------+
|   Apache Airflow |     Daily at 08:00 UTC
|   (Scheduler)    |
+--------+---------+
         |
         v
+--------+---------+     +-------------------+     +-----------------+
|    EXTRACT       | --> |    TRANSFORM      | --> |      LOAD       |
| Scrape YC,       |     | Clean text (NLTK) |     | Deduplicate     |
| Wellfound, HN    |     | Extract skills    |     | Validate        |
| in parallel      |     |   (TF-IDF +       |     | Append to       |
|                  |     |    taxonomy)       |     |   BigQuery      |
|                  |     | Market metrics    |     |                 |
+------------------+     +-------------------+     +-----------------+
                                                          |
                                                          v
                                                   +-----------+
                                                   |  BigQuery  |
                                                   | 3 tables:  |
                                                   | raw_jobs   |
                                                   | skill_     |
                                                   |   trends   |
                                                   | market_    |
                                                   |   metrics  |
                                                   +-----+-----+
                                                         |
                                                         v
                                                   +-----------+
                                                   | Streamlit  |
                                                   | Dashboard  |
                                                   +-----------+
```

## Data Sources

| Source | Method | Data |
|--------|--------|------|
| [Work at a Startup](https://www.workatastartup.com/jobs) (YC) | Playwright (JS-rendered) | Role, company, description, salary, YC batch |
| [Wellfound](https://wellfound.com/jobs) | Playwright (JS-rendered) | Role, company, description, salary, equity, stage |
| [HN "Who is Hiring?"](https://news.ycombinator.com/) | HN Firebase API | Monthly thread, 500+ postings per thread |

The pipeline scrapes all three sources daily, yielding hundreds of unique job postings per run after deduplication.

## Tech Stack

| Component | Technology | Purpose |
|-----------|-----------|---------|
| Orchestration | Apache Airflow 2.11.0 | Schedule and monitor ETL pipeline |
| Data Warehouse | Google BigQuery | Store and query structured data |
| Visualization | Streamlit | Interactive analytics dashboard |
| Scraping | Playwright + BeautifulSoup | Headless browser for JS-rendered pages |
| NLP | NLTK + scikit-learn TF-IDF | Text cleaning and skill extraction |
| Infrastructure | Docker Compose | Container orchestration |
| Database | PostgreSQL 15 | Airflow metadata storage |

## ETL Pipeline

The Airflow DAG (`startup_pulse_pipeline`) runs daily at 08:00 UTC and executes 7 tasks:

```
scrape_yc --------\
scrape_wellfound ---+--> clean_and_normalize --+--> extract_skills --+--> load_to_bigquery
scrape_hn --------/                            +--> aggregate_metrics-+
```

### Extract
- Three scrapers run in parallel — one per source
- YC and Wellfound use Playwright (headless Chromium) for JS-rendered SPAs
- HN uses the free Firebase API (no browser needed)
- Each scraper normalizes data into a shared schema before writing to disk

### Transform
Two parallel processing steps after text cleaning:

1. **Skill Extraction** (TF-IDF + Taxonomy): Matches job descriptions against a curated taxonomy of 60+ tech skills across 4 categories (languages, frameworks, infra/cloud, data/ML). Enriches each skill with salary correlation data.
2. **Market Metrics** (pandas): Computes per-source statistics — average salary, median salary, remote percentage, top role categories.

### Load
- Deduplicates within each run and across runs (queries existing job_ids from last 24 hours)
- Validates data (null checks, text truncation, type enforcement)
- Appends to BigQuery tables with retry logic on transient errors

## BigQuery Schema

Three tables, all partitioned by `collected_at` (DAY):

**`raw_jobs`** — Every collected job posting with original and cleaned description
- Clustered by `source, company_stage`
- Key columns: `job_id`, `company`, `title`, `salary_min`, `salary_max`, `remote`, `yc_batch`

**`skill_trends`** — Skill frequency and salary data per collection window
- Clustered by `category`
- Key columns: `skill`, `tfidf_score`, `frequency`, `avg_salary`, `num_jobs`

**`market_metrics`** — Aggregated market stats per source
- Clustered by `source, role_category`
- Key columns: `avg_salary`, `median_salary`, `remote_pct`, `total_jobs`

## Dashboard

The Streamlit dashboard (port 8501) has four views:

**Overview** — KPI cards (total jobs tracked, top skills this week, hottest companies) with top skills and subreddits tables, skill word cloud

**Skill Trends** — Bar chart of in-demand skills by frequency, word cloud visualization, category filter (languages/frameworks/infra/data), salary correlation data

**Market Metrics** — Salary distributions by source, remote vs on-site trends, jobs by company stage (seed/Series A/B), metrics over time

**Job Explorer** — Searchable, filterable table of recent job postings with source, salary, and location filters

## Project Structure

```
startup-pulse/
├── docker-compose.yml          # 5 services: postgres, airflow-init, webserver, scheduler, streamlit
├── Makefile                    # make up/down/restart/logs/build/init-bq
├── .env.example                # Template for environment variables
│
├── airflow/
│   ├── Dockerfile              # apache/airflow:2.11.0 + Playwright + Python deps
│   ├── requirements.txt        # playwright, beautifulsoup4, google-cloud-bigquery, nltk, scikit-learn
│   └── dags/
│       └── startup_pulse_dag.py
│
├── src/
│   ├── extract/
│   │   ├── yc_scraper.py          # YC Work at a Startup scraper (Playwright)
│   │   ├── wellfound_scraper.py   # Wellfound scraper (Playwright)
│   │   └── hn_scraper.py          # HN Who is Hiring? scraper (API)
│   ├── transform/
│   │   ├── text_cleaner.py        # NLTK text preprocessing pipeline
│   │   ├── skill_extractor.py     # TF-IDF + taxonomy skill extraction
│   │   └── metrics_aggregator.py  # Market statistics
│   ├── load/
│   │   └── bigquery_loader.py     # BigQuery insertion with deduplication
│   └── utils/
│       ├── config.py              # Centralized configuration + skill taxonomy
│       └── deduplication.py       # In-run and cross-run dedup logic
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
├── tests/
│   ├── test_hn_scraper.py
│   ├── test_yc_scraper.py
│   ├── test_wellfound_scraper.py
│   ├── test_text_cleaner.py
│   ├── test_skill_extractor.py
│   └── test_metrics_aggregator.py
│
└── credentials/                # GCP service account key (gitignored)
```

## Quick Start

```bash
# 1. Clone and configure
cp .env.example .env
# Edit .env with your GCP credentials

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

See [SETUP_GUIDE.md](SETUP_GUIDE.md) for detailed step-by-step instructions including GCP setup.

## Free-Tier Budget

| Resource | Free Tier Limit | Estimated Usage | Headroom |
|----------|----------------|-----------------|----------|
| BigQuery Storage | 10 GB/month | ~50 MB/month | 99.5% free |
| BigQuery Queries | 1 TB/month | ~2 GB/month | 99.8% free |

## Configuration

All pipeline settings are centralized in `src/utils/config.py`:

```python
# Data source URLs
YC_JOBS_URL = "https://www.workatastartup.com/jobs"
WELLFOUND_JOBS_URL = "https://wellfound.com/jobs"
HN_API_BASE = "https://hacker-news.firebaseio.com/v0"

# Scraping settings
SCRAPE_MAX_PAGES = 10       # Max pagination depth per source
SCRAPE_DELAY_SECONDS = 2    # Polite delay between page loads

# Skill taxonomy (60+ skills across 4 categories)
SKILL_TAXONOMY = {
    "languages": ["python", "javascript", "typescript", "go", "rust", ...],
    "frameworks": ["react", "next.js", "django", "fastapi", ...],
    "infra_and_cloud": ["aws", "docker", "kubernetes", "terraform", ...],
    "data_and_ml": ["pytorch", "spark", "airflow", "bigquery", "llm", ...],
}
```

## How It Works

### Skill Extraction

The system identifies trending tech skills using two complementary approaches:

1. **Taxonomy Matching**: A curated list of 60+ skills is matched against cleaned job descriptions using word-boundary regex. This catches known skills reliably.
2. **TF-IDF Scoring**: A `TfidfVectorizer` fits across all descriptions to surface emerging terms that aren't in the taxonomy yet. Skills are ranked by frequency and enriched with average salary data for posts mentioning that skill.

### Salary Extraction

Job postings express salaries in many formats ($150K, $150,000, $150k-$200k). The scrapers use regex patterns to normalize these into `salary_min` and `salary_max` integers, enabling salary analysis by skill, role, and source.

### Deduplication

Jobs are deduplicated at two levels:
- **Within each run**: Same job appearing in multiple scrape pages is kept once via content hashing
- **Across runs**: Before loading to BigQuery, existing `job_id` values from the last 24 hours are queried and filtered out

### Error Resilience

- Individual scraper failures don't block the pipeline — if Wellfound is down, YC and HN data still flows
- Airflow retries each task up to 2 times with exponential backoff
- BigQuery load retries on `ServiceUnavailable` errors
- Missing BigQuery tables are auto-created on first load attempt
