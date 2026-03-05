"""Reddit Trends ETL pipeline DAG.

Implements Phase 2 (extract) and Phase 3 (transform) of the pipeline.
Load tasks will be added in a later phase.
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


def transform_clean_text(**context):
    """Clean and normalize text fields of extracted posts."""
    from src.transform.text_cleaner import TextCleaner

    execution_date = context["ds"]
    input_path = f"/opt/airflow/data/raw/{execution_date}/posts.json"
    output_path = f"/opt/airflow/data/cleaned/{execution_date}/posts.json"

    cleaner = TextCleaner()
    result = cleaner.clean_posts(input_path, output_path)

    context["ti"].xcom_push(key="clean_metadata", value=result)
    return result


def transform_extract_keywords(**context):
    """Extract TF-IDF keywords from cleaned posts."""
    from src.transform.keyword_extractor import KeywordExtractor

    execution_date = context["ds"]
    input_path = f"/opt/airflow/data/cleaned/{execution_date}/posts.json"
    output_path = f"/opt/airflow/data/keywords/{execution_date}/keywords.json"

    extractor = KeywordExtractor()
    result = extractor.extract_keywords(input_path, output_path)

    context["ti"].xcom_push(key="keywords_metadata", value=result)
    return result


def transform_aggregate_metrics(**context):
    """Aggregate engagement metrics per subreddit/category."""
    from src.transform.metrics_aggregator import MetricsAggregator

    execution_date = context["ds"]
    input_path = f"/opt/airflow/data/cleaned/{execution_date}/posts.json"
    output_path = f"/opt/airflow/data/metrics/{execution_date}/metrics.json"

    aggregator = MetricsAggregator()
    result = aggregator.aggregate(input_path, output_path)

    context["ti"].xcom_push(key="metrics_metadata", value=result)
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

    transform_clean_task = PythonOperator(
        task_id="transform_clean_text",
        python_callable=transform_clean_text,
    )

    transform_keywords_task = PythonOperator(
        task_id="transform_extract_keywords",
        python_callable=transform_extract_keywords,
    )

    transform_metrics_task = PythonOperator(
        task_id="transform_aggregate_metrics",
        python_callable=transform_aggregate_metrics,
    )

    extract_task >> transform_clean_task >> transform_keywords_task >> transform_metrics_task
