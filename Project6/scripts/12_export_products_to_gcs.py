#!/usr/bin/env python3
"""
Re-package the Project 05 `products` CSV export and upload it as a single
gzipped CSV to:

    gs://${GCS_BUCKET}/${GCS_PREFIX_PRODUCTS}/ingest_date=${INGEST_DATE}/products.csv.gz

Tiny dataset (~19K rows). The script mirrors `11_export_ip_locations_to_gcs.py`
on purpose — same structure for both small reference tables makes the runbook
easier to remember.
"""

from __future__ import annotations

import gzip
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from dotenv import load_dotenv
from google.cloud import storage

from _common import configure_logging, env, ingest_date


def find_source_csv() -> Path:
    explicit = env("PRODUCTS_CSV")
    if explicit:
        p = Path(explicit).expanduser().resolve()
        if not p.exists():
            raise SystemExit(f"PRODUCTS_CSV={p} does not exist")
        return p

    run_date = env("RUN_DATE") or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    candidates = [
        Path(f"Project5/exports/products/products_{run_date}.csv").resolve(),
        Path(f"exports/products/products_{run_date}.csv").resolve(),
    ]
    for c in candidates:
        if c.exists():
            return c
    raise SystemExit(
        "Could not find products CSV. Tried:\n  - "
        + "\n  - ".join(str(c) for c in candidates)
        + "\nSet PRODUCTS_CSV to point at the file."
    )


def main() -> None:
    load_dotenv()
    log = configure_logging("export_products_to_gcs")

    bucket_name = env("GCS_BUCKET", required=True)
    prefix_root = env("GCS_PREFIX_PRODUCTS", "raw/p06/products")
    src = find_source_csv()
    target_blob_name = (
        f"{prefix_root.rstrip('/')}/ingest_date={ingest_date()}/products.csv.gz"
    )

    log.info("source: %s (%.2f MB)", src, src.stat().st_size / 1e6)
    log.info("target: gs://%s/%s", bucket_name, target_blob_name)

    bucket = storage.Client().bucket(bucket_name)
    blob = bucket.blob(target_blob_name)
    if blob.exists():
        log.warning(
            "blob already exists — refusing to overwrite (raw is immutable). "
            "Bump INGEST_DATE for a fresh ingest."
        )
        return

    with tempfile.NamedTemporaryFile(prefix="products_", suffix=".csv.gz", delete=False) as tmp:
        tmp_path = Path(tmp.name)
    try:
        with src.open("rb") as f_in, gzip.open(tmp_path, "wb", compresslevel=6) as f_out:
            shutil.copyfileobj(f_in, f_out, length=8 * 1024 * 1024)
        log.info("gzipped to %s (%.2f MB)", tmp_path, tmp_path.stat().st_size / 1e6)

        blob.upload_from_filename(str(tmp_path), content_type="application/gzip")
        log.info("DONE :: gs://%s/%s", bucket_name, target_blob_name)
    finally:
        tmp_path.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
