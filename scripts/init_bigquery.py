#!/usr/bin/env python3
"""One-time BigQuery dataset and table initialization."""

import os

from google.cloud import bigquery

from src.utils.config import BQ_LOCATION


def main() -> None:
    """Create the BigQuery dataset and tables for the Reddit trends pipeline."""
    project_id = os.environ["GCP_PROJECT_ID"]
    dataset_name = os.environ.get("BQ_DATASET", "reddit_trends")

    client = bigquery.Client(project=project_id)

    # ── Create dataset ────────────────────────────────────────────────
    dataset_ref = bigquery.DatasetReference(project_id, dataset_name)
    dataset = bigquery.Dataset(dataset_ref)
    dataset.location = BQ_LOCATION

    dataset = client.create_dataset(dataset, exists_ok=True)
    print(f"Dataset '{dataset_name}' ready (project={project_id}, location={BQ_LOCATION}).")

    full_prefix = f"{project_id}.{dataset_name}"

    # ── Table: raw_posts ──────────────────────────────────────────────
    raw_posts_schema = [
        bigquery.SchemaField("post_id", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("subreddit", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("category", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("title", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("selftext", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("cleaned_title", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("cleaned_selftext", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("author", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("score", "INTEGER", mode="REQUIRED"),
        bigquery.SchemaField("upvote_ratio", "FLOAT", mode="NULLABLE"),
        bigquery.SchemaField("num_comments", "INTEGER", mode="REQUIRED"),
        bigquery.SchemaField("url", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("permalink", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("is_self", "BOOLEAN", mode="NULLABLE"),
        bigquery.SchemaField("created_utc", "TIMESTAMP", mode="NULLABLE"),
        bigquery.SchemaField("collected_at", "TIMESTAMP", mode="REQUIRED"),
        bigquery.SchemaField("flair", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("listing_type", "STRING", mode="NULLABLE"),
    ]

    _create_table(
        client,
        table_id=f"{full_prefix}.raw_posts",
        schema=raw_posts_schema,
        partition_field="collected_at",
        clustering_fields=["subreddit", "category"],
    )

    # ── Table: keyword_trends ─────────────────────────────────────────
    keyword_trends_schema = [
        bigquery.SchemaField("keyword", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("subreddit", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("category", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("frequency", "INTEGER", mode="REQUIRED"),
        bigquery.SchemaField("tfidf_score", "FLOAT", mode="REQUIRED"),
        bigquery.SchemaField("num_posts", "INTEGER", mode="REQUIRED"),
        bigquery.SchemaField("avg_score", "FLOAT", mode="NULLABLE"),
        bigquery.SchemaField("avg_comments", "FLOAT", mode="NULLABLE"),
        bigquery.SchemaField("collected_at", "TIMESTAMP", mode="REQUIRED"),
    ]

    _create_table(
        client,
        table_id=f"{full_prefix}.keyword_trends",
        schema=keyword_trends_schema,
        partition_field="collected_at",
        clustering_fields=["category", "subreddit"],
    )

    # ── Table: subreddit_metrics ──────────────────────────────────────
    subreddit_metrics_schema = [
        bigquery.SchemaField("subreddit", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("category", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("total_posts_collected", "INTEGER", mode="REQUIRED"),
        bigquery.SchemaField("avg_score", "FLOAT", mode="NULLABLE"),
        bigquery.SchemaField("median_score", "FLOAT", mode="NULLABLE"),
        bigquery.SchemaField("max_score", "INTEGER", mode="NULLABLE"),
        bigquery.SchemaField("avg_comments", "FLOAT", mode="NULLABLE"),
        bigquery.SchemaField("total_comments", "INTEGER", mode="NULLABLE"),
        bigquery.SchemaField("avg_upvote_ratio", "FLOAT", mode="NULLABLE"),
        bigquery.SchemaField("posting_rate_per_hour", "FLOAT", mode="NULLABLE"),
        bigquery.SchemaField("collected_at", "TIMESTAMP", mode="REQUIRED"),
    ]

    _create_table(
        client,
        table_id=f"{full_prefix}.subreddit_metrics",
        schema=subreddit_metrics_schema,
        partition_field="collected_at",
        clustering_fields=["category"],
    )

    print("All tables initialized successfully.")


def _create_table(
    client: bigquery.Client,
    table_id: str,
    schema: list[bigquery.SchemaField],
    partition_field: str,
    clustering_fields: list[str],
) -> None:
    """Create a BigQuery table if it does not already exist."""
    table = bigquery.Table(table_id, schema=schema)
    table.time_partitioning = bigquery.TimePartitioning(field=partition_field)
    table.clustering_fields = clustering_fields

    table = client.create_table(table, exists_ok=True)
    print(f"Table '{table_id}' ready (partitioned by {partition_field}, clustered by {clustering_fields}).")


if __name__ == "__main__":
    main()
