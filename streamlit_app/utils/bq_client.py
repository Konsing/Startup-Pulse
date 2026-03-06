"""BigQuery client utilities for the Streamlit dashboard."""

import os

import pandas as pd
from google.cloud import bigquery

_client = None


def get_client() -> bigquery.Client:
    """Return a cached BigQuery client."""
    global _client
    if _client is None:
        _client = bigquery.Client(project=os.environ["GCP_PROJECT_ID"])
    return _client


def get_dataset() -> str:
    return os.environ.get("BQ_DATASET", "startup_pulse")


def query_df(sql: str) -> pd.DataFrame:
    """Run a SQL query and return results as a DataFrame."""
    return get_client().query(sql).to_dataframe()
