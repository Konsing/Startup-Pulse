"""Job deduplication utilities for the Startup Pulse pipeline.

Provides in-run deduplication (removing duplicate job_ids) and
cross-run deduplication by checking BigQuery for recently loaded jobs.
"""

import logging

from google.cloud import bigquery

logger = logging.getLogger(__name__)


def deduplicate_in_run(jobs: list[dict]) -> list[dict]:
    """Remove duplicate jobs within a single collection run.

    Keeps the first occurrence of each ``job_id``.

    Args:
        jobs: List of job dicts (each must have a ``job_id`` key).

    Returns:
        De-duplicated list of job dicts.
    """
    seen: dict[str, int] = {}
    result: list[dict] = []

    for job in jobs:
        job_id = job["job_id"]
        if job_id not in seen:
            seen[job_id] = len(result)
            result.append(job)

    removed = len(jobs) - len(result)
    if removed:
        logger.info("Deduplicated %d duplicate jobs within run (kept %d).", removed, len(result))
    return result


def get_existing_job_ids(client: bigquery.Client, table_ref: str) -> set:
    """Query BigQuery for job_ids from the last 24 hours.

    Args:
        client: An authenticated ``bigquery.Client``.
        table_ref: Fully-qualified table reference
            (e.g. ``project.dataset.raw_jobs``).

    Returns:
        Set of ``job_id`` strings. Returns an empty set if the table does
        not exist or the query fails (graceful on first run).
    """
    query = f"""
        SELECT DISTINCT job_id
        FROM `{table_ref}`
        WHERE collected_at >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 24 HOUR)
    """
    try:
        result = client.query(query).result()
        job_ids = {row.job_id for row in result}
        logger.info("Found %d existing job_ids in last 24h from %s.", len(job_ids), table_ref)
        return job_ids
    except Exception as exc:
        logger.warning(
            "Could not fetch existing job_ids from %s (may be first run): %s",
            table_ref,
            exc,
        )
        return set()
