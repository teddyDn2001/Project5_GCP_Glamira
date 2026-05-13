#!/usr/bin/env python3
"""
Bootstrap (or update) the BigQuery raw layer for Project 06.

Creates, idempotently:
  - dataset  : ${BQ_DATASET_RAW}  in ${BQ_LOCATION}
  - tables   : events, ip_locations, products
               with explicit JSON schemas, ingestion-time partitioning
               and cluster keys.

Run-safe: re-running this script does NOT drop data. It will:
  * create the dataset if missing
  * create each table if missing
  * patch the schema of existing tables to add new top-level columns
    (BQ supports `ALLOW_FIELD_ADDITION` at update time)

Authentication
--------------
Uses Application Default Credentials. On the VM that means the attached SA
`sa-p05-bq-loader@…` (which the operator must add to the dataset). Locally,
`gcloud auth application-default login` works.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from dotenv import load_dotenv
from google.api_core.exceptions import NotFound
from google.cloud import bigquery

from _common import configure_logging, env


SCHEMAS_DIR = Path(__file__).resolve().parents[1] / "schemas"

# (table_name, schema_file, cluster_keys, description)
TABLES = [
    (
        "events",
        "events.json",
        ["event_name", "collection", "product_id"],
        "Project 06 raw layer: Countly summary events from MongoDB (NDJSON.gz on GCS).",
    ),
    (
        "ip_locations",
        "ip_locations.json",
        ["country_short"],
        "Project 06 raw layer: IP → location enrichment from IP2Location (CSV.gz on GCS).",
    ),
    (
        "products",
        "products.json",
        ["status"],
        "Project 06 raw layer: products crawled by Project 05 (CSV.gz on GCS).",
    ),
]


def load_schema(filename: str) -> list[bigquery.SchemaField]:
    """Read a JSON schema file and convert to a list of SchemaField."""
    raw = json.loads((SCHEMAS_DIR / filename).read_text(encoding="utf-8"))
    return [bigquery.SchemaField.from_api_repr(f) for f in raw]


def ensure_dataset(client: bigquery.Client, dataset_id: str, location: str, log) -> bigquery.Dataset:
    ref = bigquery.Dataset(f"{client.project}.{dataset_id}")
    ref.location = location
    ref.description = "Project 06 — raw layer (Extract→Load via GCS + Cloud Function trigger)."
    try:
        existing = client.get_dataset(ref)
        log.info("dataset already exists: %s (location=%s)", existing.full_dataset_id, existing.location)
        return existing
    except NotFound:
        created = client.create_dataset(ref, exists_ok=True)
        log.info("dataset created: %s (location=%s)", created.full_dataset_id, created.location)
        return created


def ensure_table(
    client: bigquery.Client,
    dataset_id: str,
    table_name: str,
    schema_file: str,
    cluster_keys: list[str],
    description: str,
    log,
) -> None:
    schema = load_schema(schema_file)
    table_id = f"{client.project}.{dataset_id}.{table_name}"

    try:
        existing = client.get_table(table_id)
        log.info("table exists: %s (rows=%s)", table_id, existing.num_rows)

        # Patch schema to add any new fields. BQ requires unchanged fields to keep their order/types.
        existing_names = {f.name for f in existing.schema}
        new_fields = [f for f in schema if f.name not in existing_names]
        if new_fields:
            updated_schema = list(existing.schema) + new_fields
            existing.schema = updated_schema
            client.update_table(existing, ["schema"])
            log.info(
                "table %s patched with new fields: %s",
                table_id,
                [f.name for f in new_fields],
            )
        else:
            log.info("table %s schema is up-to-date", table_id)
        return
    except NotFound:
        pass  # we'll create it below

    table = bigquery.Table(table_id, schema=schema)
    table.description = description
    # Ingestion-time partitioning: cheap to set up, no source date column required.
    table.time_partitioning = bigquery.TimePartitioning(
        type_=bigquery.TimePartitioningType.DAY,
        # field=None ⇒ partition by load time (_PARTITIONTIME / _PARTITIONDATE).
        expiration_ms=None,
    )
    # Filtering by partition is optional in raw, but recommended for cost discipline.
    table.require_partition_filter = False
    if cluster_keys:
        table.clustering_fields = cluster_keys

    created = client.create_table(table, exists_ok=True)
    log.info(
        "table created: %s (partition=DAY by _PARTITIONDATE, cluster=%s)",
        created.full_table_id,
        cluster_keys,
    )


def main() -> None:
    load_dotenv()
    log = configure_logging("create_bq_dataset")

    project = env("GCP_PROJECT_ID", required=True)
    dataset = env("BQ_DATASET_RAW", "glamira_raw")
    location = env("BQ_LOCATION", "asia-southeast1")

    client = bigquery.Client(project=project, location=location)
    log.info("project=%s dataset=%s location=%s", project, dataset, location)

    ensure_dataset(client, dataset, location, log)

    for table_name, schema_file, cluster_keys, description in TABLES:
        ensure_table(client, dataset, table_name, schema_file, cluster_keys, description, log)

    log.info("DONE")


if __name__ == "__main__":
    main()
