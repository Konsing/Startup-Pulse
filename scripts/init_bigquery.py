#!/usr/bin/env python3
"""One-time BigQuery dataset and table initialization."""

import os

from google.cloud import bigquery

from src.utils.config import BQ_LOCATION


def main() -> None:
    """Create the BigQuery dataset and tables for the Startup Pulse pipeline."""
    project_id = os.environ["GCP_PROJECT_ID"]
    dataset_name = os.environ.get("BQ_DATASET", "startup_pulse")

    client = bigquery.Client(project=project_id)

    # ── Create dataset ────────────────────────────────────────────────
    dataset_ref = bigquery.DatasetReference(project_id, dataset_name)
    dataset = bigquery.Dataset(dataset_ref)
    dataset.location = BQ_LOCATION

    dataset = client.create_dataset(dataset, exists_ok=True)
    print(f"Dataset '{dataset_name}' ready (project={project_id}, location={BQ_LOCATION}).")

    full_prefix = f"{project_id}.{dataset_name}"

    # ── Table: raw_jobs ────────────────────────────────────────────────
    raw_jobs_schema = [
        bigquery.SchemaField("job_id", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("source", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("company", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("title", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("description", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("cleaned_description", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("salary_min", "INTEGER", mode="NULLABLE"),
        bigquery.SchemaField("salary_max", "INTEGER", mode="NULLABLE"),
        bigquery.SchemaField("currency", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("location", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("remote", "BOOLEAN", mode="NULLABLE"),
        bigquery.SchemaField("company_stage", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("yc_batch", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("equity", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("url", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("collected_at", "TIMESTAMP", mode="REQUIRED"),
    ]

    _create_table(
        client,
        table_id=f"{full_prefix}.raw_jobs",
        schema=raw_jobs_schema,
        partition_field="collected_at",
        clustering_fields=["source", "company_stage"],
    )

    # ── Table: skill_trends ────────────────────────────────────────────
    skill_trends_schema = [
        bigquery.SchemaField("skill", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("category", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("frequency", "INTEGER", mode="REQUIRED"),
        bigquery.SchemaField("tfidf_score", "FLOAT", mode="REQUIRED"),
        bigquery.SchemaField("avg_salary", "FLOAT", mode="NULLABLE"),
        bigquery.SchemaField("num_jobs", "INTEGER", mode="REQUIRED"),
        bigquery.SchemaField("collected_at", "TIMESTAMP", mode="REQUIRED"),
    ]

    _create_table(
        client,
        table_id=f"{full_prefix}.skill_trends",
        schema=skill_trends_schema,
        partition_field="collected_at",
        clustering_fields=["category"],
    )

    # ── Table: market_metrics ──────────────────────────────────────────
    market_metrics_schema = [
        bigquery.SchemaField("source", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("role_category", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("total_jobs", "INTEGER", mode="REQUIRED"),
        bigquery.SchemaField("avg_salary", "FLOAT", mode="NULLABLE"),
        bigquery.SchemaField("median_salary", "FLOAT", mode="NULLABLE"),
        bigquery.SchemaField("remote_pct", "FLOAT", mode="NULLABLE"),
        bigquery.SchemaField("top_skills", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("collected_at", "TIMESTAMP", mode="REQUIRED"),
    ]

    _create_table(
        client,
        table_id=f"{full_prefix}.market_metrics",
        schema=market_metrics_schema,
        partition_field="collected_at",
        clustering_fields=["source", "role_category"],
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
