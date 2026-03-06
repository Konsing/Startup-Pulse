# Startup Pulse — Complete Setup Guide

This guide walks you through every step needed to get the Startup Pulse platform running, from creating GCP credentials to triggering your first pipeline run.

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [Google Cloud Platform Setup](#2-google-cloud-platform-setup)
3. [Project Configuration](#3-project-configuration)
4. [Docker Setup](#4-docker-setup)
5. [Initialize BigQuery Tables](#5-initialize-bigquery-tables)
6. [Apache Airflow Setup](#6-apache-airflow-setup)
7. [Running the Pipeline](#7-running-the-pipeline)
8. [Streamlit Dashboard](#8-streamlit-dashboard)
9. [Troubleshooting](#9-troubleshooting)
10. [Maintenance and Operations](#10-maintenance-and-operations)

---

## 1. Prerequisites

Before starting, make sure you have:

- **Docker Desktop** (or Docker Engine + Docker Compose v2) installed and running
  - Minimum 4 GB RAM allocated to Docker (Airflow is memory-hungry)
  - Download: https://docs.docker.com/get-docker/
- **A Google account** (for Google Cloud Platform)
- **Git** installed

Verify Docker is working:
```bash
docker --version          # Docker version 24.x or later
docker compose version    # Docker Compose version v2.x
```

---

## 2. Google Cloud Platform Setup

You need a GCP project with BigQuery enabled and a service account key for authentication.

### Step 2.1: Set Up a Billing Account

Google requires a billing account linked to your project even to use the free tier. You will NOT be charged as long as you stay within BigQuery's free-tier limits (see Step 2.6).

1. Go to https://console.cloud.google.com/billing
2. If you don't have a billing account yet, click **"Create Account"**
3. Enter your billing details (credit/debit card required for verification)
4. Google gives new accounts **$300 in free credits** for 90 days on top of the always-free tier
5. After creating the billing account, it will be linked to new projects automatically

**If you're concerned about charges**: Go to **Billing > Budgets & Alerts** and create a budget alert for $1. You'll get an email if anything starts costing money (it shouldn't with this project's usage).

### Step 2.2: Create a GCP Project

1. Go to https://console.cloud.google.com/
2. Click the project dropdown at the top of the page (next to "Google Cloud")
3. Click **"New Project"**
4. Enter a project name: `startup-pulse` (or any name)
5. Make sure the billing account from Step 2.1 is selected
6. Click **"Create"**
7. Wait for the project to be created, then select it from the project dropdown

**Note your Project ID** — it's shown under the project name (e.g., `startup-pulse-123456`). This is NOT always the same as the project name. Look for it in the project settings or in the URL: `console.cloud.google.com/home/dashboard?project=YOUR_PROJECT_ID`

### Step 2.3: Enable the BigQuery API

1. In the GCP Console, go to **APIs & Services > Library**
   - Direct link: https://console.cloud.google.com/apis/library
2. Search for **"BigQuery API"**
3. Click on it, then click **"Enable"**
4. Wait for it to enable (usually a few seconds)

BigQuery is typically enabled by default on new projects, but verify it's active.

### Step 2.4: Create a Service Account

A service account is a non-human identity used by your application to authenticate with GCP services.

1. Go to **IAM & Admin > Service Accounts**
   - Direct link: https://console.cloud.google.com/iam-admin/serviceaccounts
2. Click **"+ Create Service Account"**
3. Fill in:
   - **Service account name**: `startup-pulse-etl`
   - **Service account ID**: auto-filled (e.g., `startup-pulse-etl@your-project.iam.gserviceaccount.com`)
   - **Description**: `Service account for Startup Pulse ETL pipeline`
4. Click **"Create and Continue"**
5. **Grant roles** — Add these two roles:
   - `BigQuery Data Editor` (roles/bigquery.dataEditor) — allows creating tables and inserting data
   - `BigQuery Job User` (roles/bigquery.jobUser) — allows running queries
6. Click **"Continue"**, then **"Done"**

### Step 2.5: Create and Download a Service Account Key

1. In the Service Accounts list, click on the service account you just created (`startup-pulse-etl`)
2. Go to the **"Keys"** tab
3. Click **"Add Key" > "Create new key"**
4. Select **"JSON"** format
5. Click **"Create"**
6. A JSON file will be downloaded to your computer

**Important**: This key file grants access to your GCP project. Keep it secure:
- Never commit it to git (it's already in `.gitignore`)
- Don't share it publicly
- Store it only in the `credentials/` directory of this project

### Step 2.6: BigQuery Free Tier Details

BigQuery's free tier includes:
- **10 GB** of storage per month
- **1 TB** of query processing per month
- **10 GB** of free data loading per month (streaming inserts excluded, but batch loads are free)

Our estimated usage:
- Storage: ~50 MB/month (well under 10 GB)
- Queries: ~2 GB/month (well under 1 TB)
- Loading: ~2 MB/day via batch loads (free)

**To stay within free tier:**
- The dashboard queries always filter by `collected_at` (last 7 days) to minimize bytes scanned
- Tables are partitioned by day and clustered, so queries scan only relevant partitions
- Don't run heavy `SELECT *` queries without a `WHERE` clause on `collected_at`

### Step 2.7: Set the BigQuery Region

By default, this project creates the BigQuery dataset in the `US` multi-region. If you want a different location, edit `src/utils/config.py`:

```python
BQ_LOCATION = "US"  # Change to "EU", "us-central1", etc.
```

---

## 3. Project Configuration

### Step 3.1: Clone the Repository

```bash
git clone https://github.com/Konsing/Startup-Pulse.git startup-pulse
cd startup-pulse
```

### Step 3.2: Create the Environment File

```bash
cp .env.example .env
```

### Step 3.3: Edit `.env` with Your Credentials

Open `.env` in your editor and fill in:

```env
# Google Cloud (from Step 2)
GCP_PROJECT_ID=startup-pulse-123456
BQ_DATASET=startup_pulse

# Airflow (leave as-is unless you have permission issues)
AIRFLOW_UID=50000
```

**Notes:**
- `BQ_DATASET` is the BigQuery dataset name. `startup_pulse` is the default.
- `AIRFLOW_UID` should match your host user's UID. Run `id -u` to check. On most Linux systems, `50000` is fine.

### Step 3.4: Place the GCP Service Account Key

Copy the JSON key file you downloaded in Step 2.5:

```bash
cp ~/Downloads/startup-pulse-123456-abc123.json credentials/service-account.json
```

The file MUST be named `service-account.json` — the Docker Compose file mounts it at this exact path.

### Step 3.5: Verify Your Setup

```bash
# Check all required files exist
ls -la .env                              # Should exist
ls -la credentials/service-account.json  # Should exist
cat .env                                 # Verify values are filled in
```

---

## 4. Docker Setup

### Step 4.1: Build the Docker Images

```bash
make build
```

This builds two custom images:
- **Airflow image**: Extends `apache/airflow:2.11.0-python3.11` with Playwright, BeautifulSoup, BigQuery client, NLTK, scikit-learn
- **Streamlit image**: Python 3.11 slim with Streamlit, Plotly, BigQuery client

First build takes 5-10 minutes (Playwright needs to download Chromium).

### Step 4.2: Start All Services

```bash
make up
```

This starts 5 containers:
1. **postgres** — Airflow's metadata database
2. **airflow-init** — One-time setup: runs database migrations and creates the admin user, then exits
3. **airflow-webserver** — The Airflow web UI (port 8080)
4. **airflow-scheduler** — Executes scheduled DAG tasks
5. **streamlit** — The analytics dashboard (port 8501)

### Step 4.3: Wait for Services to Be Ready

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

### Step 4.4: Verify Services

Open in your browser:
- **Airflow UI**: http://localhost:8080
  - Login: `admin` / `admin`
  - You should see the `startup_pulse_pipeline` DAG listed
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

## 5. Initialize BigQuery Tables

Before running the pipeline, create the BigQuery dataset and tables:

```bash
make init-bq
```

This runs `scripts/init_bigquery.py` inside the Airflow container, which:
1. Creates the `startup_pulse` dataset in your GCP project
2. Creates three tables with explicit schemas, partitioning, and clustering:
   - `raw_jobs` (partitioned by `collected_at`, clustered by `source, company_stage`)
   - `skill_trends` (partitioned by `collected_at`, clustered by `category`)
   - `market_metrics` (partitioned by `collected_at`, clustered by `source, role_category`)

Expected output:
```
Dataset 'startup_pulse' ready (project=startup-pulse-123456, location=US).
Table 'startup-pulse-123456.startup_pulse.raw_jobs' ready (partitioned by collected_at, clustered by ['source', 'company_stage']).
Table 'startup-pulse-123456.startup_pulse.skill_trends' ready (partitioned by collected_at, clustered by ['category']).
Table 'startup-pulse-123456.startup_pulse.market_metrics' ready (partitioned by collected_at, clustered by ['source', 'role_category']).
All tables initialized successfully.
```

**If this fails**, check:
- Is `credentials/service-account.json` present and valid?
- Does the service account have `BigQuery Data Editor` and `BigQuery Job User` roles?
- Is `GCP_PROJECT_ID` correct in `.env`?
- Is the BigQuery API enabled in your GCP project?

You can verify in the GCP Console: go to **BigQuery** (https://console.cloud.google.com/bigquery) and check that the `startup_pulse` dataset exists with 3 tables.

---

## 6. Apache Airflow Setup

### Step 6.1: Understand the Airflow UI

Open http://localhost:8080 and log in with `admin` / `admin`.

**Key areas:**
- **DAGs page** (home): Shows all DAGs. You should see `startup_pulse_pipeline`.
- **Toggle switch**: The DAG is paused by default (toggle is grey/off). You need to unpause it for scheduled runs.
- **Grid/Graph view**: Click on the DAG name to see task details and execution history.

### Step 6.2: Understand the DAG

The `startup_pulse_pipeline` DAG:
- **Schedule**: `0 8 * * *` — runs daily at 08:00 UTC
- **Tasks**: 7 tasks in this order:
  1. `scrape_yc` — Scrape YC Work at a Startup (parallel)
  2. `scrape_wellfound` — Scrape Wellfound job listings (parallel)
  3. `scrape_hn` — Scrape HN "Who is Hiring?" thread (parallel)
  4. `clean_and_normalize` — Merge all sources, clean text with NLTK
  5. `extract_skills` — TF-IDF + taxonomy skill extraction (parallel with metrics)
  6. `aggregate_metrics` — Market statistics (parallel with skills)
  7. `load_to_bigquery` — Deduplicate and load all data to BigQuery

### Step 6.3: Unpause the DAG (for Automatic Runs)

1. On the DAGs page, find `startup_pulse_pipeline`
2. Click the toggle switch on the left to unpause it (it turns blue)
3. The DAG will now run automatically at the scheduled time

**Note**: If you want to control when it runs, leave it paused and trigger runs manually (see next section).

---

## 7. Running the Pipeline

### Step 7.1: Trigger a Manual Run

To run the pipeline immediately (recommended for testing):

1. In the Airflow UI, click on `startup_pulse_pipeline`
2. Click the **"Play" button** (triangle icon) in the top right
3. Click **"Trigger DAG"** in the dropdown

Or use the command line:
```bash
docker compose exec airflow-webserver airflow dags trigger startup_pulse_pipeline
```

### Step 7.2: Monitor the Run

1. Click on the DAG name to go to the Grid view
2. You'll see a new column appear with tasks progressing from top to bottom
3. Each task shows:
   - **Green**: Success
   - **Yellow/Orange**: Running
   - **Red**: Failed
   - **Light green**: Queued
4. Click on any task instance to see its log output

### Step 7.3: Expected Timeline

A typical pipeline run takes 3-8 minutes:
- `scrape_yc` / `scrape_wellfound` / `scrape_hn`: 1-3 minutes (runs in parallel, Playwright scraping is the slowest)
- `clean_and_normalize`: 5-15 seconds
- `extract_skills`: 5-10 seconds
- `aggregate_metrics`: 2-5 seconds
- `load_to_bigquery`: 10-30 seconds

### Step 7.4: Verify Data in BigQuery

After a successful run, check your data:

1. Go to https://console.cloud.google.com/bigquery
2. In the left panel, expand your project > `startup_pulse` dataset
3. Click on `raw_jobs` and select the **"Preview"** tab — you should see rows
4. Try a query:
```sql
SELECT source, COUNT(*) as job_count, AVG(salary_min) as avg_min_salary
FROM `your-project.startup_pulse.raw_jobs`
GROUP BY source
ORDER BY job_count DESC
```

### Step 7.5: Check the Streamlit Dashboard

1. Go to http://localhost:8501
2. The Overview page should now show KPI cards and data tables
3. Navigate through the pages using the sidebar:
   - **Overview**: Summary metrics, top skills, hottest companies
   - **Skill Trends**: Bar chart, word cloud, salary correlations
   - **Market Metrics**: Salary distributions, remote trends, company stages
   - **Job Explorer**: Filterable job posting table

**Note**: The dashboard caches query results for 5 minutes. If you just ran the pipeline, wait a moment or refresh the page.

---

## 8. Streamlit Dashboard

### Accessing the Dashboard

The dashboard runs at http://localhost:8501 and reads directly from BigQuery.

### Dashboard Pages

#### Overview
- **KPI Cards**: Total jobs tracked, top skills this week, unique companies, active sources
- **Top Skills Table**: Most frequently mentioned skills with salary data
- **Top Companies Table**: Companies with the most open listings

#### Skill Trends
- **Category Filter**: Filter skills by languages/frameworks/infra/data & ML
- **Top Skills Bar Chart**: Horizontal bar chart colored by category
- **Word Cloud**: Visual representation of skill demand
- **Skill Details Table**: Full data with TF-IDF scores and salary averages

#### Market Metrics
- **Salary Bar Chart**: Average salary by source
- **Engagement Scatter Plot**: Salary vs. job count, sized by remote percentage
- **Metrics Over Time**: Line chart of salary and job count trends per source (after multiple pipeline runs)
- **Full Metrics Table**: All market metrics

#### Job Explorer
- **Source & Category Filters**: Dropdown filters to narrow results
- **Jobs Table**: Sortable table with company, title, salary range, location, remote status

### Customizing the Dashboard

The dashboard queries BigQuery for the last 7 days of data by default. To change this window, edit the queries in `streamlit_app/app.py` — look for `INTERVAL 7 DAY` and adjust as needed.

---

## 9. Troubleshooting

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

### Scraper Errors

**Playwright timeout or crash**:
- Increase `SCRAPE_TIMEOUT_MS` in `src/utils/config.py` (default: 60000ms)
- Check that the Airflow container has enough memory (Playwright + Chromium needs ~500MB)
- The site may have changed its layout — check the scraper's CSS selectors

**HN API returning empty results**:
- The "Who is Hiring?" thread is posted on the 1st of each month
- Between threads, the scraper returns the most recent one via Algolia search

**One scraper fails but others succeed**:
- This is by design — individual scraper failures don't block the pipeline
- Check the Airflow task logs for the specific error
- The clean/transform/load steps proceed with whatever data was collected

### Streamlit Shows "Could not load data"

- Make sure the pipeline has run at least once successfully
- Check that `credentials/service-account.json` is accessible to the Streamlit container
- Check Streamlit logs: `docker compose logs streamlit`

### Container Running Out of Memory

Airflow + PostgreSQL + Streamlit + Playwright need ~3-4 GB of RAM total. If Docker is constrained:
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

## 10. Maintenance and Operations

### Adding a New Skill to the Taxonomy

1. Edit `src/utils/config.py`:
   ```python
   SKILL_TAXONOMY = {
       "languages": ["python", "javascript", ..., "zig"],  # added
       ...
   }
   ```
2. No rebuild or restart needed — the change is picked up on the next DAG run (files are volume-mounted)

### Adding a New Data Source

Adding a fourth scraper requires:
1. Create a new scraper class in `src/extract/` following the pattern of `hn_scraper.py`
2. Add a new extract task in `airflow/dags/startup_pulse_dag.py`
3. Wire it into the DAG dependencies
4. No rebuild needed if the new scraper only uses already-installed packages

### Viewing Airflow Task Logs

1. In the Airflow UI, click on the DAG
2. Click on a specific task instance (a colored square in the grid)
3. Click **"Log"** to see detailed output including:
   - Number of jobs scraped per source
   - Number of skills extracted
   - Number of rows loaded to BigQuery
   - Any errors or warnings

### Checking Pipeline Health

```bash
# View container status
docker compose ps

# View recent Airflow logs
docker compose logs --tail=100 airflow-scheduler

# Check if the DAG ran recently
docker compose exec airflow-webserver airflow dags list-runs -d startup_pulse_pipeline
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
