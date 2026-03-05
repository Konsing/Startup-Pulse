"""Post deduplication utilities for the Reddit Trends pipeline.

Provides in-run deduplication (merging hot+top duplicates) and
cross-run deduplication by checking BigQuery for recently loaded posts.
"""

import logging

from google.cloud import bigquery

logger = logging.getLogger(__name__)


def deduplicate_in_run(posts: list[dict]) -> list[dict]:
    """Remove duplicate posts within a single collection run.

    If the same ``post_id`` appears in both hot and top listings, keep the
    first occurrence but set ``listing_type`` to ``'hot+top'``.

    Args:
        posts: List of post dicts (each must have ``post_id`` and
            ``listing_type`` keys).

    Returns:
        De-duplicated list of post dicts.
    """
    seen: dict[str, int] = {}  # post_id -> index in result list
    result: list[dict] = []

    for post in posts:
        post_id = post["post_id"]
        if post_id in seen:
            idx = seen[post_id]
            existing_type = result[idx]["listing_type"]
            if existing_type != "hot+top":
                result[idx]["listing_type"] = "hot+top"
                logger.debug("Merged duplicate post_id=%s -> listing_type=hot+top", post_id)
        else:
            seen[post_id] = len(result)
            result.append(post)

    removed = len(posts) - len(result)
    if removed:
        logger.info("Deduplicated %d duplicate posts within run (kept %d).", removed, len(result))
    return result


def get_existing_post_ids(client: bigquery.Client, table_ref: str) -> set:
    """Query BigQuery for post_ids from the last 24 hours.

    Args:
        client: An authenticated ``bigquery.Client``.
        table_ref: Fully-qualified table reference
            (e.g. ``project.dataset.raw_posts``).

    Returns:
        Set of ``post_id`` strings. Returns an empty set if the table does
        not exist or the query fails (graceful on first run).
    """
    query = f"""
        SELECT DISTINCT post_id
        FROM `{table_ref}`
        WHERE collected_at >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 24 HOUR)
    """
    try:
        result = client.query(query).result()
        post_ids = {row.post_id for row in result}
        logger.info("Found %d existing post_ids in last 24h from %s.", len(post_ids), table_ref)
        return post_ids
    except Exception as exc:
        logger.warning(
            "Could not fetch existing post_ids from %s (may be first run): %s",
            table_ref,
            exc,
        )
        return set()
