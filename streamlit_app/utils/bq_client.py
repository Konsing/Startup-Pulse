"""BigQuery client utilities for the Streamlit dashboard."""

import os

import pandas as pd
import streamlit as st
from google.cloud import bigquery
from google.oauth2 import service_account

_client = None


def get_client() -> bigquery.Client:
    """Return a cached BigQuery client.

    Supports two auth modes:
    - GOOGLE_APPLICATION_CREDENTIALS env var (local Docker)
    - Streamlit secrets with [gcp_service_account] section (Streamlit Cloud)
    """
    global _client
    if _client is not None:
        return _client

    project = os.environ.get("GCP_PROJECT_ID") or st.secrets.get("GCP_PROJECT_ID")

    if os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
        _client = bigquery.Client(project=project)
    else:
        credentials = service_account.Credentials.from_service_account_info(
            st.secrets["gcp_service_account"]
        )
        _client = bigquery.Client(project=project, credentials=credentials)

    return _client


def get_dataset() -> str:
    return os.environ.get("BQ_DATASET") or st.secrets.get("BQ_DATASET", "startup_pulse")


def query_df(sql: str) -> pd.DataFrame:
    """Run a SQL query and return results as a DataFrame."""
    return get_client().query(sql).to_dataframe()
