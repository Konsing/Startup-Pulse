# Startup Pulse -- Design Document

Startup job market intelligence platform. Scrapes startup job postings daily,
extracts skills and market signals using NLP, loads into BigQuery, and visualizes
trends through a Streamlit dashboard.

Transforms the existing reddit-trends repo into startup-pulse.

## Data Sources

| Source | Method | Data | Frequency |
|--------|--------|------|-----------|
| workatastartup.com | Playwright (JS-rendered SPA) | Role, company, description, salary, location, YC batch | Daily |
| Wellfound (angel.co/jobs) | Playwright (JS-rendered SPA) | Role, company, description, salary, equity, stage | Daily |
| HN "Who is Hiring?" | HN Firebase API (no scraping) | Monthly thread, 500+ postings, plain text | Monthly |

## Pipeline (Airflow DAG)

```
scrape_yc --------\
scrape_wellfound ---+--> clean_and_normalize --+--> extract_skills --+--> load_to_bigquery
scrape_hn --------/                            +--> market_metrics --+
```

- 3 extract tasks run in parallel (one per source)
- clean_and_normalize: standardize fields across sources, deduplicate by company+title
- extract_skills: TF-IDF + regex patterns for tech stacks, role categories, seniority
- market_metrics: aggregate stats per category/source/week
- load_to_bigquery: append to BigQuery with dedup and retry

## BigQuery Tables

### raw_jobs
| Column | Type | Mode |
|--------|------|------|
| job_id | STRING | REQUIRED |
| source | STRING | REQUIRED |
| company | STRING | REQUIRED |
| title | STRING | REQUIRED |
| description | STRING | NULLABLE |
| cleaned_description | STRING | NULLABLE |
| salary_min | INTEGER | NULLABLE |
| salary_max | INTEGER | NULLABLE |
| currency | STRING | NULLABLE |
| location | STRING | NULLABLE |
| remote | BOOLEAN | NULLABLE |
| company_stage | STRING | NULLABLE |
| yc_batch | STRING | NULLABLE |
| equity | STRING | NULLABLE |
| url | STRING | NULLABLE |
| collected_at | TIMESTAMP | REQUIRED |

Partitioned by: collected_at
Clustered by: source, company_stage

### skill_trends
| Column | Type | Mode |
|--------|------|------|
| skill | STRING | REQUIRED |
| category | STRING | REQUIRED |
| frequency | INTEGER | REQUIRED |
| tfidf_score | FLOAT | REQUIRED |
| avg_salary | FLOAT | NULLABLE |
| num_jobs | INTEGER | REQUIRED |
| collected_at | TIMESTAMP | REQUIRED |

Partitioned by: collected_at
Clustered by: category

### market_metrics
| Column | Type | Mode |
|--------|------|------|
| source | STRING | REQUIRED |
| role_category | STRING | REQUIRED |
| total_jobs | INTEGER | REQUIRED |
| avg_salary | FLOAT | NULLABLE |
| median_salary | FLOAT | NULLABLE |
| remote_pct | FLOAT | NULLABLE |
| top_skills | STRING | NULLABLE |
| collected_at | TIMESTAMP | REQUIRED |

Partitioned by: collected_at
Clustered by: source, role_category

## Streamlit Dashboard

4 pages with radio sidebar navigation:

1. Overview: KPI cards (total jobs, top skills, hottest companies), skill word cloud
2. Skill Trends: rising/falling skills over time, filter by role category, bar + line charts
3. Market Metrics: jobs by company stage, remote vs on-site, salary distributions
4. Job Explorer: searchable/filterable table of recent postings

## NLP Pipeline

- Text cleaning: NLTK (same as reddit-trends)
- Skill extraction: TF-IDF (scikit-learn) on cleaned descriptions + curated skill taxonomy regex matching
- Role classification: keyword-based categorization (backend, frontend, ML, devops, etc.)
- Salary extraction: regex patterns for "$X-$Y", "$Xk-$Yk", currency normalization
- Seniority detection: keyword matching (junior, senior, staff, lead, principal)

## Infrastructure

- Docker Compose: postgres, airflow-init, airflow-webserver, airflow-scheduler, streamlit
- Airflow: LocalExecutor, apache/airflow:2.11.0-python3.11
- New dependency: Playwright (for JS-rendered scraping)
- BigQuery: free tier (10 GB storage, 1 TB queries/month)
- All runs locally, GCP free tier only

## What Transfers from reddit-trends

- Docker Compose structure (x-airflow-common anchor pattern)
- BigQuery loader with dedup + retry logic (bigquery_loader.py, deduplication.py)
- NLP pipeline pattern (clean -> extract -> aggregate)
- Streamlit caching pattern (@st.cache_data)
- Makefile targets
- init_bigquery.py table creation pattern

## What Changes

- Extract layer: PRAW -> Playwright/BeautifulSoup scrapers
- Config: subreddit list -> job board URLs + CSS selectors
- Transform: Reddit post cleaning -> job description parsing
- New: salary extraction module
- New: skill taxonomy (curated tech skills list)
- New: role classifier
