# Project 06 — Architecture & Design Decisions

> Goal: extend the Project 05 foundation (GCS lake + VM + MongoDB) with an
> automated pipeline that lands raw data into BigQuery's `raw` layer through
> a Cloud Function trigger. This is the "Extract → Load" half of an ELT
> design; transforms (dbt) and serving (Looker) come in a later project.

```
┌────────────────┐    ┌──────────────────┐    ┌──────────────────┐    ┌────────────────────┐
│  MongoDB (VM)  │    │ Google Cloud     │    │ Cloud Function   │    │ BigQuery           │
│  + CSV exports │ ─► │ Storage (lake)   │ ─► │ (Eventarc Gen 2) │ ─► │ glamira_raw.*      │
│  Project 05    │    │ raw/p06/...      │    │ trigger_bq_load  │    │ raw layer (3 tbl)  │
└────────────────┘    └──────────────────┘    └──────────────────┘    └────────────────────┘
       Extract              Load (immutable)         Trigger                 Raw warehouse
```

---

## 1. Why these design choices?

### 1.1 File formats

| Source                        | Volume     | Format chosen      | Reason                                                                                         |
| ----------------------------- | ---------- | ------------------ | ---------------------------------------------------------------------------------------------- |
| `countly.summary` (Mongo)     | ~41M docs  | **NDJSON + gzip**  | Mongo docs are deeply nested → JSONL keeps fidelity; BigQuery loads `.json.gz` natively; no extra deps. |
| `ip_locations` (P05 export)   | 3.24M rows | **CSV + gzip**     | Already CSV from P05; flat schema; tiny enough that CSV is fine.                               |
| `products` (P05 export)       | ~19K rows  | **CSV + gzip**     | Same as IP locations — flat, small, already produced by P05.                                   |

We deliberately rejected Parquet for raw events: while it compresses ~10× better, it
forces us to flatten / type-cast nested Mongo fields *before* the data ever reaches the
warehouse, which violates the "raw is faithful to the source" principle of a layered DW.
Flattening belongs in the dbt staging layer, not in the export step.

### 1.2 GCS layout (audit-friendly, immutable)

We **reuse** the Project 05 bucket `gs://unigap-prj5-raw` (single bucket, multiple
prefixes — easier IAM and cost tracking) but with a dedicated, partition-style prefix
for Project 06 so Eventarc filters only fire on our paths:

```
gs://unigap-prj5-raw/
└── raw/
    └── p06/
        ├── events/         ingest_date=2026-05-10/   events_part-00000.ndjson.gz
        ├── ip_locations/   ingest_date=2026-05-10/   ip_locations.csv.gz
        └── products/       ingest_date=2026-05-10/   products.csv.gz
```

Rules:

- **Immutable**: re-runs use a new `ingest_date=...` directory. We never overwrite a
  finalized object. (BigQuery load jobs are idempotent at the table level, but GCS
  objects are not — so we treat the lake as append-only.)
- **Path encodes routing**: the second-level prefix (`events|ip_locations|products`) is
  the only piece the Cloud Function needs to map an arriving file to a BQ table.

### 1.3 Cloud Function trigger

- **Generation 2** (Eventarc-backed): better cold start, supports up to 60 min execution,
  easier IAM, future-proof. Gen 1 is in maintenance mode.
- **Event type**: `google.cloud.storage.object.v1.finalized` on bucket
  `unigap-prj5-raw`.
- **Path filter**: function rejects events whose `name` doesn't start with
  `raw/p06/` (cheap defense — Eventarc doesn't natively filter by prefix beyond bucket).
- **Idempotency**: BigQuery `LoadJob` with explicit `job_id` deterministically derived
  from the GCS object's `generation` ⇒ retries are no-ops, not duplicates.
- **Failure mode**: any exception is re-raised so Eventarc retries (default Pub/Sub
  retry policy applies) and the failure is visible in Cloud Logging.

### 1.4 BigQuery `raw` layer

- **Dataset**: `glamira_raw` in region `asia-southeast1` (same region as the bucket
  → no egress, faster loads).
- **Tables** (one per source — *no transformations* in raw layer):
  - `events`        ← NDJSON loads, schema autodetect-friendly but we pin an explicit
    schema with the high-traffic top-level fields and a `JSON` column for the rest.
  - `ip_locations`  ← CSV loads, fully typed.
  - `products`      ← CSV loads, fully typed.
- **Partitioning**: `_PARTITIONDATE` (a.k.a. ingestion-time partitioning) so we don't
  have to derive a date column from each source. Cheaper queries, simpler loads.
- **Clustering**:
  - `events`        cluster by `event_name`, `product_id` — most common filter columns.
  - `ip_locations`  cluster by `country_short` — typical geo aggregations.
  - `products`      cluster by `status` — typical "did this crawl succeed?" lookups.
- **Write disposition**: `WRITE_APPEND` for events (every file is a new partition slice);
  `WRITE_TRUNCATE` for IP locations / products (small reference tables fully refreshed
  per ingest_date).

### 1.5 Identity & permissions (least-privilege, reusing P05 SAs)

| Component                      | Identity                                      | Roles                                                                                              |
| ------------------------------ | --------------------------------------------- | -------------------------------------------------------------------------------------------------- |
| VM export (`scripts/10_*.py`)  | `sa-p05-vm-ingest@…` (already attached to VM) | `roles/storage.objectAdmin` on `gs://unigap-prj5-raw` (already granted in P05)                    |
| Cloud Function                 | `sa-p05-bq-loader@…`                          | `roles/storage.objectViewer` on bucket, `roles/bigquery.dataEditor` on dataset, `roles/bigquery.jobUser` on project |
| Eventarc agent                 | `service-…@gcp-sa-eventarc.iam.gserviceaccount.com` | `roles/eventarc.eventReceiver`, `roles/run.invoker` (auto-granted by `gcloud functions deploy`)    |

We do **not** create new keys for these SAs — the VM uses its attached SA via ADC,
and the Cloud Function runs as the SA configured at deploy time.

---

## 2. Idempotency, retries, and "what happens on failure?"

| Step                | Failure mode                              | Recovery behaviour                                                                                       |
| ------------------- | ----------------------------------------- | -------------------------------------------------------------------------------------------------------- |
| Mongo → NDJSON      | SSH drop / VM crash mid-export            | Each batch file is finalized atomically (resumable upload). On rerun, we skip files already on GCS by name. |
| GCS upload          | Network blip                              | `google-cloud-storage` resumable uploads retry transparently up to default deadline.                     |
| Cloud Function      | BigQuery load job fails (bad row, schema) | Function raises → Eventarc retries with backoff. Persistent failures show up as red bars in Cloud Logging. |
| BigQuery load       | Duplicate trigger for same file           | Deterministic `job_id` (= sha1 of bucket+name+generation) → second submission is rejected as "Already Exists". |

---

## 3. Operational runbook (high level — see `README.md` for commands)

1. **Export** raw events from Mongo → GCS, plus repackage P05 CSVs → GCS.
2. **Bootstrap** BQ dataset & tables (one-shot, idempotent).
3. **Deploy** Cloud Function with Eventarc trigger.
4. **Smoke test**: upload a 1-row sample to each prefix, watch CF logs, verify rows in BQ.
5. **Full run**: kick off the events export on the VM (in `tmux`), watch logs.
6. **Profile**: run `scripts/30_data_profiling.py` to produce the DQ report.

---

## 4. What's intentionally out of scope for Project 06

- dbt transformations (Project 07).
- Looker dashboards (Project 08).
- Streaming ingestion (this is a daily-batch pipeline).
- Schema evolution beyond "add new top-level field" — drift is logged, not auto-applied.
