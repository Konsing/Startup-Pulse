"""Startup Pulse ETL pipeline DAG.

Scrapes startup job boards daily, cleans and analyzes postings
with NLP, and loads results into BigQuery.
"""

import pendulum
from airflow.models.dag import DAG
from airflow.operators.python import PythonOperator

default_args = {
    "owner": "startup-pulse",
    "retries": 2,
    "retry_delay": pendulum.duration(minutes=5),
    "retry_exponential_backoff": True,
    "execution_timeout": pendulum.duration(minutes=30),
}


def scrape_yc(**context):
    """Scrape YC Work at a Startup."""
    from src.extract.yc_scraper import YCScraper
    execution_date = context["ds"]
    output_dir = f"/opt/airflow/data/raw/yc/{execution_date}"
    result = YCScraper().scrape(output_dir)
    context["ti"].xcom_push(key="yc_metadata", value=result)
    return result


def scrape_greenhouse(**context):
    """Scrape Greenhouse job boards."""
    from src.extract.greenhouse_scraper import GreenhouseScraper
    execution_date = context["ds"]
    output_dir = f"/opt/airflow/data/raw/greenhouse/{execution_date}"
    result = GreenhouseScraper().scrape(output_dir)
    context["ti"].xcom_push(key="greenhouse_metadata", value=result)
    return result


def scrape_ashby(**context):
    """Scrape Ashby ATS job boards."""
    from src.extract.ashby_scraper import AshbyScraper
    execution_date = context["ds"]
    output_dir = f"/opt/airflow/data/raw/ashby/{execution_date}"
    result = AshbyScraper().scrape(output_dir)
    context["ti"].xcom_push(key="ashby_metadata", value=result)
    return result


def scrape_hn(**context):
    """Scrape HN Who is Hiring thread."""
    from src.extract.hn_scraper import HNScraper
    execution_date = context["ds"]
    output_dir = f"/opt/airflow/data/raw/hn/{execution_date}"
    result = HNScraper().scrape(output_dir)
    context["ti"].xcom_push(key="hn_metadata", value=result)
    return result


def scrape_lever(**context):
    """Scrape Lever job boards."""
    from src.extract.lever_scraper import LeverScraper
    execution_date = context["ds"]
    output_dir = f"/opt/airflow/data/raw/lever/{execution_date}"
    result = LeverScraper().scrape(output_dir)
    context["ti"].xcom_push(key="lever_metadata", value=result)
    return result


def clean_and_normalize(**context):
    """Merge all scraped jobs and clean text fields."""
    import json
    import os
    from pathlib import Path
    from src.transform.text_cleaner import TextCleaner

    execution_date = context["ds"]
    all_jobs = []

    for source in ("yc", "greenhouse", "ashby", "hn", "lever"):
        path = f"/opt/airflow/data/raw/{source}/{execution_date}/jobs.json"
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as fh:
                all_jobs.extend(json.load(fh))

    cleaner = TextCleaner()
    cleaned = cleaner.clean_jobs(all_jobs)

    output_dir = f"/opt/airflow/data/cleaned/{execution_date}"
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    output_path = os.path.join(output_dir, "jobs.json")
    with open(output_path, "w", encoding="utf-8") as fh:
        json.dump(cleaned, fh, ensure_ascii=False, indent=2)

    context["ti"].xcom_push(key="clean_metadata", value={"total_jobs": len(cleaned)})
    return {"total_jobs": len(cleaned)}


def extract_skills(**context):
    """Extract skill trends from cleaned jobs."""
    import json
    import os
    from pathlib import Path
    from src.transform.skill_extractor import SkillExtractor

    execution_date = context["ds"]
    input_path = f"/opt/airflow/data/cleaned/{execution_date}/jobs.json"
    with open(input_path, "r", encoding="utf-8") as fh:
        jobs = json.load(fh)

    results = SkillExtractor().extract(jobs)

    output_dir = f"/opt/airflow/data/skills/{execution_date}"
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    output_path = os.path.join(output_dir, "skills.json")
    with open(output_path, "w", encoding="utf-8") as fh:
        json.dump(results, fh, ensure_ascii=False, indent=2)

    context["ti"].xcom_push(key="skills_metadata", value={"total_skills": len(results)})
    return {"total_skills": len(results)}


def aggregate_metrics(**context):
    """Aggregate market metrics from cleaned jobs."""
    import json
    import os
    from pathlib import Path
    from src.transform.metrics_aggregator import MetricsAggregator

    execution_date = context["ds"]
    input_path = f"/opt/airflow/data/cleaned/{execution_date}/jobs.json"
    with open(input_path, "r", encoding="utf-8") as fh:
        jobs = json.load(fh)

    results = MetricsAggregator().aggregate(jobs)

    output_dir = f"/opt/airflow/data/metrics/{execution_date}"
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    output_path = os.path.join(output_dir, "metrics.json")
    with open(output_path, "w", encoding="utf-8") as fh:
        json.dump(results, fh, ensure_ascii=False, indent=2)

    context["ti"].xcom_push(key="metrics_metadata", value={"sources": len(results)})
    return {"sources": len(results)}


def load_to_bigquery(**context):
    """Load all transformed data into BigQuery."""
    from src.load.bigquery_loader import BigQueryLoader
    execution_date = context["ds"]
    loader = BigQueryLoader()
    result = loader.load_all(
        cleaned_path=f"/opt/airflow/data/cleaned/{execution_date}/jobs.json",
        skills_path=f"/opt/airflow/data/skills/{execution_date}/skills.json",
        metrics_path=f"/opt/airflow/data/metrics/{execution_date}/metrics.json",
    )
    context["ti"].xcom_push(key="load_metadata", value=result)
    return result


with DAG(
    dag_id="startup_pulse_pipeline",
    default_args=default_args,
    description="Scrape startup job boards, extract skills with NLP, load to BigQuery",
    schedule="0 8 * * *",
    start_date=pendulum.datetime(2026, 3, 1, tz="UTC"),
    catchup=False,
    max_active_runs=1,
    tags=["jobs", "nlp", "bigquery", "etl", "startups"],
) as dag:

    scrape_yc_task = PythonOperator(task_id="scrape_yc", python_callable=scrape_yc)
    scrape_greenhouse_task = PythonOperator(task_id="scrape_greenhouse", python_callable=scrape_greenhouse)
    scrape_ashby_task = PythonOperator(task_id="scrape_ashby", python_callable=scrape_ashby)
    scrape_hn_task = PythonOperator(task_id="scrape_hn", python_callable=scrape_hn)
    scrape_lever_task = PythonOperator(task_id="scrape_lever", python_callable=scrape_lever)

    clean_task = PythonOperator(task_id="clean_and_normalize", python_callable=clean_and_normalize)

    skills_task = PythonOperator(task_id="extract_skills", python_callable=extract_skills)
    metrics_task = PythonOperator(task_id="aggregate_metrics", python_callable=aggregate_metrics)

    load_task = PythonOperator(task_id="load_to_bigquery", python_callable=load_to_bigquery)

    # 4 scrapers in parallel -> clean -> [skills, metrics] in parallel -> load
    [scrape_yc_task, scrape_greenhouse_task, scrape_ashby_task, scrape_hn_task, scrape_lever_task] >> clean_task
    clean_task >> [skills_task, metrics_task]
    [skills_task, metrics_task] >> load_task
