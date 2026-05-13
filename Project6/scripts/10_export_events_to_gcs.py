#!/usr/bin/env python3
"""
Export `countly.summary` (≈41M docs) from MongoDB on the VM to GCS as
sharded NDJSON.gz files under:

    gs://${GCS_BUCKET}/${GCS_PREFIX_EVENTS}/ingest_date=${INGEST_DATE}/
        events_part-00000.ndjson.gz
        events_part-00001.ndjson.gz
        ...

Design notes
------------
* **Streaming, not all-in-memory**: we hold a Mongo cursor open and stream
  documents through gzip → resumable GCS upload. Memory stays bounded.
* **Batched into shards**: each output file holds at most EVENTS_BATCH_SIZE
  documents. Smaller, well-sized shards (~hundreds of MB) parallelise BigQuery
  loads better than one giant 200 GB file would.
* **Resumable / idempotent**: before a shard is uploaded we check if a blob
  with the same name already exists on GCS (e.g. from a previous run that
  finished that shard). If yes, we skip it. So a re-run after a network drop
  picks up where the previous one stopped — provided we use the same
  INGEST_DATE.
* **Atomic finalisation**: each shard is uploaded as a single resumable upload;
  failures abort that shard but don't leave a half-written file at the final
  blob name (GCS finalises only on success).
* **Bson → JSON**: we use `bson.json_util.dumps` with relaxed mode, so
  ObjectId / Date / NumberLong all become well-formed JSON values BigQuery
  understands (or can ignore via JSON column).
"""

from __future__ import annotations

import gzip
import io
import os
import sys
from pathlib import Path

# allow running as `python3 scripts/10_export_events_to_gcs.py` from Project6/
sys.path.insert(0, str(Path(__file__).resolve().parent))

from bson import json_util
from dotenv import load_dotenv
from google.cloud import storage
from pymongo import MongoClient

from _common import configure_logging, env, ingest_date, mongo_uri


def main() -> None:
    load_dotenv()
    log = configure_logging("export_events_to_gcs")

    bucket_name = env("GCS_BUCKET", required=True)
    prefix_root = env("GCS_PREFIX_EVENTS", "raw/p06/events")
    raw_db = env("RAW_DB", "countly")
    raw_coll = env("RAW_COLL", "summary")
    batch_size = int(env("EVENTS_BATCH_SIZE", "200000"))
    max_docs = int(env("EVENTS_MAX_DOCS", "0"))
    chunk_mb = int(env("EVENTS_UPLOAD_CHUNK_MB", "8"))

    run_dir = f"{prefix_root.rstrip('/')}/ingest_date={ingest_date()}"
    log.info("source: mongo://%s.%s", raw_db, raw_coll)
    log.info("target: gs://%s/%s", bucket_name, run_dir)
    log.info("batch_size=%d max_docs=%d chunk_mb=%d", batch_size, max_docs, chunk_mb)

    client = MongoClient(mongo_uri())
    src = client[raw_db][raw_coll]

    estimated_total = src.estimated_document_count()
    log.info("estimated total documents: %d", estimated_total)

    gcs = storage.Client()
    bucket = gcs.bucket(bucket_name)

    cursor = src.find({}, no_cursor_timeout=True, batch_size=2000)

    shard_idx = 0
    docs_in_shard = 0
    total_written = 0
    total_skipped_shards = 0

    buf = io.BytesIO()
    gz = gzip.GzipFile(fileobj=buf, mode="wb", compresslevel=6)

    def shard_blob_name(idx: int) -> str:
        return f"{run_dir}/events_part-{idx:05d}.ndjson.gz"

    def flush_shard(idx: int) -> None:
        nonlocal buf, gz, docs_in_shard, total_skipped_shards
        if docs_in_shard == 0:
            return
        gz.close()
        payload = buf.getvalue()
        blob = bucket.blob(shard_blob_name(idx))
        if blob.exists():
            log.info(
                "shard %05d already on GCS (%s) — skipping (resume mode)",
                idx,
                blob.name,
            )
            total_skipped_shards += 1
        else:
            blob.chunk_size = chunk_mb * 1024 * 1024
            blob.upload_from_string(
                payload,
                content_type="application/gzip",
            )
            log.info(
                "shard %05d uploaded :: docs=%d gz_bytes=%d gs://%s/%s",
                idx,
                docs_in_shard,
                len(payload),
                bucket_name,
                blob.name,
            )
        # reset buffer for next shard
        buf = io.BytesIO()
        gz = gzip.GzipFile(fileobj=buf, mode="wb", compresslevel=6)
        docs_in_shard = 0

    try:
        for doc in cursor:
            if max_docs and total_written >= max_docs:
                log.info("EVENTS_MAX_DOCS=%d reached — stopping early", max_docs)
                break

            line = json_util.dumps(doc, json_options=json_util.RELAXED_JSON_OPTIONS)
            gz.write(line.encode("utf-8"))
            gz.write(b"\n")

            docs_in_shard += 1
            total_written += 1

            if docs_in_shard >= batch_size:
                flush_shard(shard_idx)
                shard_idx += 1

            if total_written % 100_000 == 0:
                pct = (100.0 * total_written / estimated_total) if estimated_total else 0
                log.info(
                    "progress: %d docs written (~%.1f%%), shards finalised=%d",
                    total_written,
                    pct,
                    shard_idx,
                )

        # flush the last partial shard
        if docs_in_shard > 0:
            flush_shard(shard_idx)
            shard_idx += 1

    finally:
        cursor.close()
        if not gz.closed:
            gz.close()
        client.close()

    log.info(
        "DONE :: total_docs=%d shards_uploaded=%d shards_skipped=%d target=gs://%s/%s",
        total_written,
        shard_idx - total_skipped_shards,
        total_skipped_shards,
        bucket_name,
        run_dir,
    )


if __name__ == "__main__":
    main()
