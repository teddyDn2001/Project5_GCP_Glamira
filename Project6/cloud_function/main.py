"""
Cloud Function (Gen 2) — Eventarc trigger that loads new GCS objects into BigQuery.

Trigger: google.cloud.storage.object.v1.finalized on bucket ${CF_TRIGGER_BUCKET}.
Routing : decided by `routing.route(object_name)` (see routing.py).
Identity: runs as ${CF_SERVICE_ACCOUNT} (sa-p05-bq-loader by default).

Behavioural contract
--------------------
* If the object is NOT a Project 06 file → log and return 0 (success, no-op).
* If routing matches → submit a BigQuery LoadJob with a deterministic job_id.
* On retry / duplicate event → BQ rejects the second job ("Already Exists") and
  we treat it as success, NOT as an error, so Eventarc stops retrying.
* On real failure → re-raise so Eventarc retries with backoff and the error
  shows up in Cloud Logging with severity=ERROR.

Local debug
-----------
    pip install -r requirements.txt
    functions-framework --target=trigger_bigquery_load --signature-type=cloudevent
    # then POST a synthetic CloudEvent (see README for example).
"""

from __future__ import annotations

import logging
import os

import functions_framework
from cloudevents.http import CloudEvent
from google.api_core.exceptions import Conflict
from google.cloud import bigquery

from routing import LoadTarget, deterministic_job_id, route


LOG = logging.getLogger("p06-loader")
LOG.setLevel(logging.INFO)


# ---- Config from environment (set at deploy time) ----------------------------

GCP_PROJECT = os.environ["GCP_PROJECT_ID"]
BQ_DATASET = os.environ.get("BQ_DATASET_RAW", "glamira_raw")
BQ_LOCATION = os.environ.get("BQ_LOCATION", "asia-southeast1")
JOB_ID_PREFIX = os.environ.get("BQ_JOB_ID_PREFIX", "p06_load")


# Singleton client (re-used across warm invocations to avoid auth handshake cost).
_BQ: bigquery.Client | None = None


def _bq_client() -> bigquery.Client:
    global _BQ
    if _BQ is None:
        _BQ = bigquery.Client(project=GCP_PROJECT, location=BQ_LOCATION)
    return _BQ


def _build_load_config(target: LoadTarget) -> bigquery.LoadJobConfig:
    cfg = bigquery.LoadJobConfig()
    cfg.source_format = target.source_format
    cfg.write_disposition = target.write_disposition
    cfg.ignore_unknown_values = target.ignore_unknown_values
    if target.skip_leading_rows:
        cfg.skip_leading_rows = target.skip_leading_rows
    if target.allow_field_addition:
        cfg.schema_update_options = [bigquery.SchemaUpdateOption.ALLOW_FIELD_ADDITION]
    # Schema is taken from the destination table (created by scripts/20_create_bq_dataset.py).
    return cfg


@functions_framework.cloud_event
def trigger_bigquery_load(event: CloudEvent) -> None:
    """Entry point referenced by `--entry-point trigger_bigquery_load` at deploy time."""
    data = event.data or {}
    bucket = data.get("bucket")
    name = data.get("name")
    generation = data.get("generation")
    size = data.get("size")
    event_id = event["id"]

    LOG.info(
        "received event id=%s bucket=%s name=%s generation=%s size=%s",
        event_id, bucket, name, generation, size,
    )

    if not bucket or not name:
        LOG.warning("event missing bucket/name — ignoring")
        return

    target = route(name)
    if target is None:
        LOG.info("no routing rule matched object=%s — ignoring", name)
        return

    table_ref = f"{GCP_PROJECT}.{BQ_DATASET}.{target.table}"
    uri = f"gs://{bucket}/{name}"
    job_id = deterministic_job_id(JOB_ID_PREFIX, bucket, name, generation)

    LOG.info(
        "starting BQ load :: job_id=%s uri=%s -> %s (format=%s, write=%s)",
        job_id, uri, table_ref, target.source_format, target.write_disposition,
    )

    try:
        load_job = _bq_client().load_table_from_uri(
            uri,
            table_ref,
            job_id=job_id,
            location=BQ_LOCATION,
            job_config=_build_load_config(target),
        )
    except Conflict:
        # Same generation already triggered a load (Eventarc retry / duplicate). Idempotent path.
        LOG.info("BQ load job %s already exists — duplicate event, treating as success", job_id)
        return

    # Wait synchronously so the function only returns AFTER BQ has finished.
    # This makes errors surface as function failures (Eventarc will retry).
    load_job.result()

    LOG.info(
        "BQ load done :: job_id=%s rows_loaded=%s output_bytes=%s table=%s",
        load_job.job_id,
        load_job.output_rows,
        load_job.output_bytes,
        table_ref,
    )
