#!/usr/bin/env python3
"""
Manual loader: GCS → BigQuery for Project 06.

Used for:
  * Backfills (replay all files under a prefix).
  * Smoke-testing the routing logic without going through Eventarc.
  * Disaster recovery if the Cloud Function is paused.

Reuses the SAME `routing.py` module the Cloud Function uses, so file-routing
behaviour cannot drift between the two code paths.

Examples
--------
# Load everything for a given ingest_date:
python3 scripts/21_load_gcs_to_bq.py --ingest-date 2026-05-10

# Load just one specific blob:
python3 scripts/21_load_gcs_to_bq.py \
    --uri gs://unigap-prj5-raw/raw/p06/events/ingest_date=2026-05-10/events_part-00000.ndjson.gz

# Dry-run (print what *would* be loaded):
python3 scripts/21_load_gcs_to_bq.py --ingest-date 2026-05-10 --dry-run
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Make the repo importable so we can reuse cloud_function/routing.py
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "cloud_function"))

from dotenv import load_dotenv
from google.api_core.exceptions import Conflict
from google.cloud import bigquery, storage

from _common import configure_logging, env, ingest_date
from routing import LoadTarget, deterministic_job_id, route


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = p.add_mutually_exclusive_group()
    g.add_argument("--uri", help="Single gs:// URI to load.")
    g.add_argument(
        "--ingest-date",
        help="Process all files under raw/p06/*/ingest_date=<DATE>/. Defaults to env INGEST_DATE.",
    )
    p.add_argument("--dry-run", action="store_true", help="Print what would happen, do not submit jobs.")
    p.add_argument("--prefix", default="raw/p06", help="Top-level prefix to scan (default: raw/p06).")
    return p.parse_args()


def list_blobs_for_date(gcs: storage.Client, bucket: str, prefix: str, date: str):
    full_prefix = f"{prefix.rstrip('/')}/"
    for blob in gcs.list_blobs(bucket, prefix=full_prefix):
        # Match only blobs whose path contains ingest_date=<DATE>
        if f"ingest_date={date}/" not in blob.name:
            continue
        yield blob


def build_job_config(target: LoadTarget) -> bigquery.LoadJobConfig:
    cfg = bigquery.LoadJobConfig()
    cfg.source_format = target.source_format
    cfg.write_disposition = target.write_disposition
    cfg.ignore_unknown_values = target.ignore_unknown_values
    if target.skip_leading_rows:
        cfg.skip_leading_rows = target.skip_leading_rows
    if target.allow_field_addition:
        cfg.schema_update_options = [bigquery.SchemaUpdateOption.ALLOW_FIELD_ADDITION]
    return cfg


def submit_load(
    bq: bigquery.Client,
    project: str,
    dataset: str,
    location: str,
    bucket: str,
    blob_name: str,
    generation: int | str | None,
    target: LoadTarget,
    log,
    *,
    dry_run: bool,
) -> None:
    table_ref = f"{project}.{dataset}.{target.table}"
    uri = f"gs://{bucket}/{blob_name}"
    job_id = deterministic_job_id("p06_manual", bucket, blob_name, generation)

    log.info(
        "load :: %s -> %s (format=%s write=%s job_id=%s)",
        uri, table_ref, target.source_format, target.write_disposition, job_id,
    )
    if dry_run:
        return

    try:
        job = bq.load_table_from_uri(
            uri, table_ref, job_id=job_id, location=location,
            job_config=build_job_config(target),
        )
    except Conflict:
        log.info("job %s already exists — skipping (idempotent)", job_id)
        return
    job.result()
    log.info("done :: rows_loaded=%s output_bytes=%s", job.output_rows, job.output_bytes)


def main() -> None:
    load_dotenv()
    args = parse_args()
    log = configure_logging("load_gcs_to_bq")

    project = env("GCP_PROJECT_ID", required=True)
    dataset = env("BQ_DATASET_RAW", "glamira_raw")
    location = env("BQ_LOCATION", "asia-southeast1")
    bucket = env("GCS_BUCKET", required=True)

    bq = bigquery.Client(project=project, location=location)
    gcs = storage.Client(project=project)

    # --uri mode: load a single object
    if args.uri:
        if not args.uri.startswith("gs://"):
            raise SystemExit(f"--uri must start with gs:// (got {args.uri!r})")
        path = args.uri[len("gs://"):]
        bkt, _, name = path.partition("/")
        blob = gcs.bucket(bkt).get_blob(name)
        if blob is None:
            raise SystemExit(f"Object not found: {args.uri}")
        target = route(blob.name)
        if target is None:
            log.warning("no routing rule matched %s — nothing to do", blob.name)
            return
        submit_load(bq, project, dataset, location, bkt, blob.name, blob.generation, target, log, dry_run=args.dry_run)
        return

    # --ingest-date mode: scan and load everything for a date
    date = args.ingest_date or ingest_date()
    log.info("scanning gs://%s/%s/ for ingest_date=%s", bucket, args.prefix, date)
    matched = 0
    for blob in list_blobs_for_date(gcs, bucket, args.prefix, date):
        target = route(blob.name)
        if target is None:
            log.debug("skip (no rule): %s", blob.name)
            continue
        matched += 1
        submit_load(bq, project, dataset, location, bucket, blob.name, blob.generation, target, log, dry_run=args.dry_run)

    log.info("done :: %d files matched and processed", matched)


if __name__ == "__main__":
    main()
