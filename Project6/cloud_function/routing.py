"""
Routing rules: GCS object name -> BigQuery target table & load config.

Single source of truth for "which file goes where".
Imported by:
  * cloud_function/main.py  (production trigger)
  * scripts/21_load_gcs_to_bq.py  (manual / replay loader)

Keeping it as a tiny pure-Python module (no GCP deps) makes it trivially unit-testable.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass


@dataclass(frozen=True)
class LoadTarget:
    table: str           # short table name within the dataset (e.g. "events")
    source_format: str   # "NEWLINE_DELIMITED_JSON" | "CSV"
    write_disposition: str  # "WRITE_APPEND" | "WRITE_TRUNCATE"
    skip_leading_rows: int = 0
    ignore_unknown_values: bool = False
    # When True, the loader will set schema_update_options=["ALLOW_FIELD_ADDITION"]
    allow_field_addition: bool = False


# Each rule: (compiled regex, LoadTarget). First match wins.
# We anchor on the Project 06 prefix so unrelated objects in the bucket are ignored.
_RULES: list[tuple[re.Pattern[str], LoadTarget]] = [
    (
        re.compile(r"^raw/p06/events/ingest_date=\d{4}-\d{2}-\d{2}/events_part-\d+\.ndjson\.gz$"),
        LoadTarget(
            table="events",
            source_format="NEWLINE_DELIMITED_JSON",
            write_disposition="WRITE_APPEND",
            ignore_unknown_values=True,
            allow_field_addition=True,
        ),
    ),
    (
        re.compile(r"^raw/p06/ip_locations/ingest_date=\d{4}-\d{2}-\d{2}/ip_locations\.csv\.gz$"),
        LoadTarget(
            table="ip_locations",
            source_format="CSV",
            write_disposition="WRITE_TRUNCATE",
            skip_leading_rows=1,
            ignore_unknown_values=False,
            allow_field_addition=False,
        ),
    ),
    (
        re.compile(r"^raw/p06/products/ingest_date=\d{4}-\d{2}-\d{2}/products\.csv\.gz$"),
        LoadTarget(
            table="products",
            source_format="CSV",
            write_disposition="WRITE_TRUNCATE",
            skip_leading_rows=1,
            ignore_unknown_values=False,
            allow_field_addition=False,
        ),
    ),
]


def route(object_name: str) -> LoadTarget | None:
    """Return the load target for a given GCS object name, or None if no rule matches.

    No-match means "this is not a Project 06 file" — the caller should ignore it.
    """
    for pattern, target in _RULES:
        if pattern.match(object_name):
            return target
    return None


def deterministic_job_id(prefix: str, bucket: str, name: str, generation: str | int | None) -> str:
    """Build a stable BigQuery job_id from the GCS object's identity.

    Two retries of the same Eventarc event ⇒ same job_id ⇒ BigQuery rejects the
    second submission with `Already Exists`, which is exactly the idempotency
    semantics we want.
    """
    h = hashlib.sha1(f"{bucket}/{name}@{generation or 0}".encode("utf-8")).hexdigest()[:32]
    # job_id must be <=1024 chars and match [A-Za-z0-9_-]
    safe_prefix = re.sub(r"[^A-Za-z0-9_-]", "_", prefix)[:48]
    return f"{safe_prefix}_{h}"
