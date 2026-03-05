"""Reddit Trends ETL pipeline DAG.

Currently implements Phase 2 (extract). Transform and load tasks
will be added in later phases.
"""

from datetime import datetime

import pendulum
from airflow.models.dag import DAG
from airflow.operators.python import PythonOperator

default_args = {
    "owner": "reddit-trends",
    "retries": 2,
    "retry_delay": pendulum.duration(minutes=5),
    "retry_exponential_backoff": True,
    "execution_timeout": pendulum.duration(minutes=30),
}


def extract_reddit_posts(**context):
    """Extract posts from Reddit using PRAW."""
    from src.extract.reddit_collector import RedditCollector

    execution_date = context["ds"]
    output_dir = f"/opt/airflow/data/raw/{execution_date}"

    collector = RedditCollector()
    result = collector.collect_posts(output_dir)

    # Push metadata to XCom for monitoring
    context["ti"].xcom_push(key="extract_metadata", value=result)
    return result


with DAG(
    dag_id="reddit_trends_pipeline",
    default_args=default_args,
    description="Extract Reddit posts, transform with NLP, load to BigQuery",
    schedule="0 */6 * * *",
    start_date=pendulum.datetime(2026, 3, 1, tz="UTC"),
    catchup=False,
    max_active_runs=1,
    tags=["reddit", "nlp", "bigquery", "etl"],
) as dag:

    extract_task = PythonOperator(
        task_id="extract_reddit_posts",
        python_callable=extract_reddit_posts,
    )
