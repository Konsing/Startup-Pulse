# Reddit Trends Platform - Complete Setup Guide

This guide walks you through every step needed to get the Reddit Trends Analysis Platform running, from creating API credentials to triggering your first pipeline run.

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [Reddit API Setup](#2-reddit-api-setup)
3. [Google Cloud Platform Setup](#3-google-cloud-platform-setup)
4. [Project Configuration](#4-project-configuration)
5. [Docker Setup](#5-docker-setup)
6. [Initialize BigQuery Tables](#6-initialize-bigquery-tables)
7. [Apache Airflow Setup](#7-apache-airflow-setup)
8. [Running the Pipeline](#8-running-the-pipeline)
9. [Streamlit Dashboard](#9-streamlit-dashboard)
10. [Troubleshooting](#10-troubleshooting)
11. [Maintenance and Operations](#11-maintenance-and-operations)

---

## 1. Prerequisites

Before starting, make sure you have:

- **Docker Desktop** (or Docker Engine + Docker Compose v2) installed and running
  - Minimum 4 GB RAM allocated to Docker (Airflow is memory-hungry)
  - Download: https://docs.docker.com/get-docker/
- **A Google account** (for Google Cloud Platform)
- **A Reddit account** (for API access)
- **Git** installed

Verify Docker is working:
```bash
docker --version          # Docker version 24.x or later
docker compose version    # Docker Compose version v2.x
```

---

## 2. Reddit API Setup

You need Reddit API credentials to collect posts. Reddit provides free API access for personal/script use.

### Step 2.1: Create a Reddit App

1. Log in to your Reddit account
2. Go to https://www.reddit.com/prefs/apps
3. Scroll to the bottom and click **"create another app..."**
4. Fill in the form:
   - **Name**: `reddit-trends` (or any name you like)
   - **App type**: Select **"script"** (this is important — "script" is for personal use and doesn't require a redirect URI)
   - **Description**: `Reddit trend analysis pipeline`
   - **About URL**: leave blank
   - **Redirect URI**: `http://localhost:8080` (required but not used for script apps)
5. Click **"create app"**

### Step 2.2: Note Your Credentials

After creating the app, you'll see:

```
reddit-trends
personal use script
─────────────────────
<CLIENT_ID>              <-- this is directly under "personal use script"
secret: <CLIENT_SECRET>  <-- click "edit" if you need to reveal it
```

You need three values:
- **Client ID**: The string directly under "personal use script" (looks like `a1b2c3d4e5f6g7`)
- **Client Secret**: The string after "secret:" (looks like `H8i9J0k1L2m3N4o5P6q7R8s9T0`)
- **User Agent**: A descriptive string identifying your app. Format: `platform:app_name:version (by /u/your_username)`. Example: `reddit-trends:v1.0 (by /u/yourusername)`

### Step 2.3: Understand Rate Limits

Reddit's API allows:
- **60 requests per minute** for OAuth-authenticated apps
- Our pipeline makes ~18 requests per run (9 subreddits x 2 listing types), with 1-second sleeps between calls
- Running every 6 hours = ~72 requests/day — well within limits

---

## 3. Google Cloud Platform Setup

You need a GCP project with BigQuery enabled and a service account key for authentication.

### Step 3.1: Create a GCP Project

1. Go to https://console.cloud.google.com/
2. Click the project dropdown at the top of the page (next to "Google Cloud")
3. Click **"New Project"**
4. Enter a project name: `reddit-trends` (or any name)
5. Click **"Create"**
6. Wait for the project to be created, then select it from the project dropdown

**Note your Project ID** — it's shown under the project name (e.g., `reddit-trends-123456`). This is NOT always the same as the project name. Look for it in the project settings or in the URL: `console.cloud.google.com/home/dashboard?project=YOUR_PROJECT_ID`

### Step 3.2: Enable the BigQuery API

1. In the GCP Console, go to **APIs & Services > Library**
   - Direct link: https://console.cloud.google.com/apis/library
2. Search for **"BigQuery API"**
3. Click on it, then click **"Enable"**
4. Wait for it to enable (usually a few seconds)

BigQuery is typically enabled by default on new projects, but verify it's active.

### Step 3.3: Create a Service Account

A service account is a non-human identity used by your application to authenticate with GCP services.

1. Go to **IAM & Admin > Service Accounts**
   - Direct link: https://console.cloud.google.com/iam-admin/serviceaccounts
2. Click **"+ Create Service Account"**
3. Fill in:
   - **Service account name**: `reddit-trends-etl`
   - **Service account ID**: auto-filled (e.g., `reddit-trends-etl@your-project.iam.gserviceaccount.com`)
   - **Description**: `Service account for Reddit Trends ETL pipeline`
4. Click **"Create and Continue"**
5. **Grant roles** — Add these two roles:
   - `BigQuery Data Editor` (roles/bigquery.dataEditor) — allows creating tables and inserting data
   - `BigQuery Job User` (roles/bigquery.jobUser) — allows running queries
6. Click **"Continue"**, then **"Done"**

### Step 3.4: Create and Download a Service Account Key

1. In the Service Accounts list, click on the service account you just created (`reddit-trends-etl`)
2. Go to the **"Keys"** tab
3. Click **"Add Key" > "Create new key"**
4. Select **"JSON"** format
5. Click **"Create"**
6. A JSON file will be downloaded to your computer (e.g., `reddit-trends-123456-abc123.json`)

**Important**: This key file grants access to your GCP project. Keep it secure:
- Never commit it to git (it's already in `.gitignore`)
- Don't share it publicly
- Store it only in the `credentials/` directory of this project

### Step 3.5: BigQuery Free Tier Details

BigQuery's free tier includes:
- **10 GB** of storage per month
- **1 TB** of query processing per month
- **10 GB** of free data loading per month (streaming inserts excluded, but batch loads are free)

Our estimated usage:
- Storage: ~140 MB/month (well under 10 GB)
- Queries: ~3 GB/month (well under 1 TB)
- Loading: ~4 MB/day via batch loads (free)

**To stay within free tier:**
- The dashboard queries always filter by `collected_at` (last 7 days) to minimize bytes scanned
- Tables are partitioned by day and clustered, so queries scan only relevant partitions
- Don't run heavy `SELECT *` queries without a `WHERE` clause on `collected_at`

### Step 3.6: Set the BigQuery Region

By default, this project creates the BigQuery dataset in the `US` multi-region. If you want a different location, edit `src/utils/config.py`:

```python
BQ_LOCATION = "US"  # Change to "EU", "us-central1", etc.
```

---

## 4. Project Configuration

### Step 4.1: Create the Environment File

```bash
cd reddit-trends
cp .env.example .env
```

### Step 4.2: Edit `.env` with Your Credentials

Open `.env` in your editor and fill in:

```env
# Reddit API credentials (from Step 2)
REDDIT_CLIENT_ID=a1b2c3d4e5f6g7
REDDIT_CLIENT_SECRET=H8i9J0k1L2m3N4o5P6q7R8s9T0
REDDIT_USER_AGENT=reddit-trends:v1.0 (by /u/yourusername)

# Google Cloud (from Step 3)
GCP_PROJECT_ID=reddit-trends-123456
BQ_DATASET=reddit_trends

# Airflow (leave as-is unless you have permission issues)
AIRFLOW_UID=50000
```

**Notes:**
- `REDDIT_USER_AGENT` must follow Reddit's format guidelines. Using a generic user agent may get rate-limited.
- `BQ_DATASET` is the BigQuery dataset name. `reddit_trends` is the default.
- `AIRFLOW_UID` should match your host user's UID. Run `id -u` to check. On most Linux systems, `50000` is fine.

### Step 4.3: Place the GCP Service Account Key

Copy the JSON key file you downloaded in Step 3.4:

```bash
cp ~/Downloads/reddit-trends-123456-abc123.json credentials/service-account.json
```

The file MUST be named `service-account.json` — the Docker Compose file mounts it at this exact path.

### Step 4.4: Verify Your Setup

```bash
# Check all required files exist
ls -la .env                           # Should exist
ls -la credentials/service-account.json  # Should exist
cat .env                              # Verify values are filled in
```

---

## 5. Docker Setup

### Step 5.1: Build the Docker Images

```bash
make build
```

This builds two custom images:
- **Airflow image**: Extends `apache/airflow:2.11.0-python3.11` with PRAW, BigQuery client, NLTK, scikit-learn
- **Streamlit image**: Python 3.11 slim with Streamlit, Plotly, BigQuery client

First build takes 3-5 minutes (downloading base images + installing Python packages).

### Step 5.2: Start All Services

```bash
make up
```

This starts 5 containers:
1. **postgres** — Airflow's metadata database
2. **airflow-init** — One-time setup: runs database migrations and creates the admin user, then exits
3. **airflow-webserver** — The Airflow web UI (port 8080)
4. **airflow-scheduler** — Executes scheduled DAG tasks
5. **streamlit** — The analytics dashboard (port 8501)

### Step 5.3: Wait for Services to Be Ready

```bash
# Watch the logs until you see "airflow-webserver" reporting healthy
make logs

# Or check container status
docker compose ps
```

Wait until you see:
- `airflow-init` has exited with code 0
- `airflow-webserver` shows status "healthy"
- `airflow-scheduler` shows status "running"
- `streamlit` shows status "running"

This typically takes 30-60 seconds after `make up`.

### Step 5.4: Verify Services

Open in your browser:
- **Airflow UI**: http://localhost:8080
  - Login: `admin` / `admin`
  - You should see the `reddit_trends_pipeline` DAG listed
- **Streamlit**: http://localhost:8501
  - You'll see "Could not load data from BigQuery" — this is expected before the first pipeline run

### Docker Commands Reference

```bash
make up        # Start all containers in background
make down      # Stop and remove all containers
make restart   # Stop then start all containers
make logs      # Stream logs from all containers (Ctrl+C to exit)
make build     # Rebuild Docker images (after changing requirements.txt or Dockerfiles)
```

---

## 6. Initialize BigQuery Tables

Before running the pipeline, create the BigQuery dataset and tables:

```bash
make init-bq
```

This runs `scripts/init_bigquery.py` inside the Airflow container, which:
1. Creates the `reddit_trends` dataset in your GCP project
2. Creates three tables with explicit schemas, partitioning, and clustering:
   - `raw_posts` (partitioned by `collected_at`, clustered by `subreddit, category`)
   - `keyword_trends` (partitioned by `collected_at`, clustered by `category, subreddit`)
   - `subreddit_metrics` (partitioned by `collected_at`, clustered by `category`)

Expected output:
```
Dataset 'reddit_trends' ready (project=reddit-trends-123456, location=US).
Table 'reddit-trends-123456.reddit_trends.raw_posts' ready (partitioned by collected_at, clustered by ['subreddit', 'category']).
Table 'reddit-trends-123456.reddit_trends.keyword_trends' ready (partitioned by collected_at, clustered by ['category', 'subreddit']).
Table 'reddit-trends-123456.reddit_trends.subreddit_metrics' ready (partitioned by collected_at, clustered by ['category']).
All tables initialized successfully.
```

**If this fails**, check:
- Is `credentials/service-account.json` present and valid?
- Does the service account have `BigQuery Data Editor` and `BigQuery Job User` roles?
- Is `GCP_PROJECT_ID` correct in `.env`?
- Is the BigQuery API enabled in your GCP project?

You can verify in the GCP Console: go to **BigQuery** (https://console.cloud.google.com/bigquery) and check that the `reddit_trends` dataset exists with 3 tables.

---

## 7. Apache Airflow Setup

### Step 7.1: Understand the Airflow UI

Open http://localhost:8080 and log in with `admin` / `admin`.

**Key areas:**
- **DAGs page** (home): Shows all DAGs. You should see `reddit_trends_pipeline`.
- **Toggle switch**: The DAG is paused by default (toggle is grey/off). You need to unpause it for scheduled runs.
- **Grid/Graph view**: Click on the DAG name to see task details and execution history.

### Step 7.2: Understand the DAG

The `reddit_trends_pipeline` DAG:
- **Schedule**: `0 */6 * * *` — runs at 00:00, 06:00, 12:00, 18:00 UTC
- **Tasks**: 5 tasks in this order:
  1. `extract_reddit_posts` — Collects ~900 posts from 9 subreddits
  2. `transform_clean_text` — Cleans and normalizes text
  3. `transform_extract_keywords` — TF-IDF keyword extraction (runs in parallel with metrics)
  4. `transform_aggregate_metrics` — Engagement statistics (runs in parallel with keywords)
  5. `load_to_bigquery` — Deduplicates and loads to BigQuery

### Step 7.3: Unpause the DAG (for Automatic Runs)

1. On the DAGs page, find `reddit_trends_pipeline`
2. Click the toggle switch on the left to unpause it (it turns blue)
3. The DAG will now run automatically at the scheduled times

**Note**: If you want to control when it runs, leave it paused and trigger runs manually (see next section).

---

## 8. Running the Pipeline

### Step 8.1: Trigger a Manual Run

To run the pipeline immediately (recommended for testing):

1. In the Airflow UI, click on `reddit_trends_pipeline`
2. Click the **"Play" button** (triangle icon) in the top right
3. Click **"Trigger DAG"** in the dropdown

Or use the command line:
```bash
docker compose exec airflow-webserver airflow dags trigger reddit_trends_pipeline
```

### Step 8.2: Monitor the Run

1. Click on the DAG name to go to the Grid view
2. You'll see a new column appear with tasks progressing from top to bottom
3. Each task shows:
   - **Green**: Success
   - **Yellow/Orange**: Running
   - **Red**: Failed
   - **Light green**: Queued
4. Click on any task instance to see its log output

### Step 8.3: Expected Timeline

A typical pipeline run takes 2-5 minutes:
- `extract_reddit_posts`: 30-90 seconds (depends on Reddit API response times)
- `transform_clean_text`: 5-15 seconds
- `transform_extract_keywords`: 5-10 seconds
- `transform_aggregate_metrics`: 2-5 seconds
- `load_to_bigquery`: 10-30 seconds

### Step 8.4: Verify Data in BigQuery

After a successful run, check your data:

1. Go to https://console.cloud.google.com/bigquery
2. In the left panel, expand your project > `reddit_trends` dataset
3. Click on `raw_posts` and select the **"Preview"** tab — you should see rows
4. Try a query:
```sql
SELECT subreddit, COUNT(*) as post_count, AVG(score) as avg_score
FROM `your-project.reddit_trends.raw_posts`
GROUP BY subreddit
ORDER BY avg_score DESC
```

### Step 8.5: Check the Streamlit Dashboard

1. Go to http://localhost:8501
2. The Overview page should now show KPI cards and data tables
3. Navigate through the pages using the sidebar:
   - **Overview**: Summary metrics and top keywords/subreddits
   - **Keyword Trends**: Bar chart, word cloud, keyword details
   - **Subreddit Metrics**: Engagement charts and comparisons
   - **Recent Posts**: Filterable post table

**Note**: The dashboard caches query results for 5 minutes. If you just ran the pipeline, wait a moment or refresh the page.

---

## 9. Streamlit Dashboard

### Accessing the Dashboard

The dashboard runs at http://localhost:8501 and reads directly from BigQuery.

### Dashboard Pages

#### Overview
- **KPI Cards**: Subreddits tracked, total posts, average score, unique keywords
- **Top Keywords Table**: Highest TF-IDF scoring keywords across all subreddits
- **Top Subreddits Table**: Subreddits ranked by average post score

#### Keyword Trends
- **Category Filter**: Filter keywords by technology/finance/gaming
- **Top Keywords Bar Chart**: Horizontal bar chart colored by subreddit
- **Word Cloud**: Visual representation of keyword importance
- **Keyword Details Table**: Full keyword data with TF-IDF scores

#### Subreddit Metrics
- **Score Bar Chart**: Average post score by subreddit, colored by category
- **Engagement Scatter Plot**: Score vs. comments, sized by post count
- **Metrics Over Time**: Line chart of score/comments trends per subreddit (after multiple pipeline runs)
- **Full Metrics Table**: All metrics for all subreddits

#### Recent Posts
- **Category & Subreddit Filters**: Dropdown filters to narrow results
- **Posts Table**: Sortable table with title, score, comments, upvote ratio, listing type

### Customizing the Dashboard

The dashboard queries BigQuery for the last 7 days of data by default. To change this window, edit the queries in `streamlit_app/app.py` — look for `INTERVAL 7 DAY` and adjust as needed.

---

## 10. Troubleshooting

### "Permission Denied" on Docker

If you get permission errors running Docker commands:
```bash
# Add your user to the docker group (Linux)
sudo usermod -aG docker $USER
# Log out and back in for changes to take effect
```

### Airflow Webserver Not Starting

Check logs:
```bash
docker compose logs airflow-webserver
docker compose logs airflow-init
```

Common causes:
- PostgreSQL not ready yet — wait and retry
- Port 8080 already in use — stop the conflicting service or change the port in `docker-compose.yml`

### "AIRFLOW_UID is not set" Warning

Set it in your `.env` file:
```bash
# Get your user ID
id -u
# Add to .env
echo "AIRFLOW_UID=$(id -u)" >> .env
```

### BigQuery Authentication Errors

**"Could not automatically determine credentials"**:
- Verify `credentials/service-account.json` exists
- Verify `GOOGLE_APPLICATION_CREDENTIALS` path is correct in `docker-compose.yml`
- Rebuild containers: `make build && make restart`

**"Access Denied" or "403 Forbidden"**:
- Check that your service account has `BigQuery Data Editor` and `BigQuery Job User` roles
- Verify the project ID in `.env` matches the project where the service account was created

**"Dataset not found"**:
- Run `make init-bq` to create the dataset and tables

### Reddit API Errors

**"401 Unauthorized"**:
- Verify `REDDIT_CLIENT_ID` and `REDDIT_CLIENT_SECRET` in `.env`
- Make sure you selected "script" type when creating the Reddit app
- Check that the Reddit app hasn't been deleted

**"429 Too Many Requests"**:
- The pipeline has built-in rate limiting (1-second sleep between calls)
- If you're running the pipeline too frequently, increase `API_SLEEP_SECONDS` in `src/utils/config.py`

**"403 Forbidden" for a specific subreddit**:
- The subreddit may be private or quarantined
- The pipeline handles this gracefully — it logs a warning and continues with other subreddits
- Remove the problematic subreddit from `SUBREDDIT_CONFIG` in `src/utils/config.py`

### Streamlit Shows "Could not load data"

- Make sure the pipeline has run at least once successfully
- Check that `credentials/service-account.json` is accessible to the Streamlit container
- Check Streamlit logs: `docker compose logs streamlit`

### Container Running Out of Memory

Airflow + PostgreSQL + Streamlit need ~2-3 GB of RAM total. If Docker is constrained:
- Increase Docker Desktop's memory allocation (Settings > Resources > Memory)
- Minimum recommended: 4 GB

### Rebuilding After Code Changes

If you modify Python files in `src/` or `streamlit_app/`:
- Changes to `src/`, `airflow/dags/`, or `streamlit_app/` are **live-mounted** — they take effect immediately (no rebuild needed)
- Changes to `Dockerfile` or `requirements.txt` files require a rebuild:
  ```bash
  make build && make restart
  ```

---

## 11. Maintenance and Operations

### Adding a New Subreddit

1. Edit `src/utils/config.py`:
   ```python
   SUBREDDIT_CONFIG = {
       "technology": ["technology", "programming", "artificial", "machinelearning"],  # added
       ...
   }
   ```
2. No rebuild or restart needed — the change is picked up on the next DAG run (files are volume-mounted)

### Adding a New Category

1. Edit `src/utils/config.py`:
   ```python
   SUBREDDIT_CONFIG = {
       ...
       "science": ["science", "askscience", "space"],  # new category
   }
   ```
2. No rebuild needed

### Viewing Airflow Task Logs

1. In the Airflow UI, click on the DAG
2. Click on a specific task instance (a colored square in the grid)
3. Click **"Log"** to see detailed output including:
   - Number of posts collected per subreddit
   - Number of keywords extracted
   - Number of rows loaded to BigQuery
   - Any errors or warnings

### Checking Pipeline Health

```bash
# View container status
docker compose ps

# View recent Airflow logs
docker compose logs --tail=100 airflow-scheduler

# Check if the DAG ran recently
docker compose exec airflow-webserver airflow dags list-runs -d reddit_trends_pipeline
```

### Stopping the Platform

```bash
# Stop all containers (data in BigQuery persists)
make down

# To also remove Docker volumes (PostgreSQL data, logs):
docker compose down -v
```

### Backing Up

- **BigQuery data** persists in Google Cloud — no local backup needed
- **Airflow metadata** (DAG run history, task logs) is in the PostgreSQL volume
- **Pipeline code** should be committed to git

### Cost Monitoring

Monitor your BigQuery usage in the GCP Console:
1. Go to https://console.cloud.google.com/billing
2. Or check BigQuery directly: **BigQuery > Admin > Resource Management**
3. Set up billing alerts if desired (though free-tier usage is minimal)
