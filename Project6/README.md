# Project 06 — Automated Data Pipeline & Storage (GCS → Cloud Function → BigQuery)

> **Builds on Project 05** (GCS lake `unigap-prj5-raw`, VM `p05-mongo-vm` with
> MongoDB, IP2Location & Products CSVs already on GCS). This project adds the
> **Extract → Load** half of the lakehouse: exports raw events to the lake,
> wires up an Eventarc Cloud Function to auto-load each new GCS file into
> BigQuery's `raw` layer, and produces a data profiling report.

```
MongoDB (VM)  ─►  GCS (data lake)  ──[Cloud Function trigger]──►  BigQuery (raw)
+ P05 CSVs                                                     events / ip_locations / products
```

Detailed design rationale lives in [`ARCHITECTURE.md`](./ARCHITECTURE.md).

---

## Repo layout

```
Project6/
├── README.md                       # this file (the runbook)
├── ARCHITECTURE.md                 # design decisions
├── .env.example                    # template environment
├── requirements.txt                # local / VM Python deps
├── schemas/
│   ├── events.json                 # explicit BQ schema for events
│   ├── ip_locations.json
│   └── products.json
├── sql/                            # profiling SQL templates
│   ├── profiling_events.sql
│   ├── profiling_ip_locations.sql
│   └── profiling_products.sql
├── scripts/                        # local / VM-side scripts
│   ├── _common.py                  # logging + env helpers
│   ├── 10_export_events_to_gcs.py  # MongoDB → NDJSON.gz → GCS  (the heavy one)
│   ├── 11_export_ip_locations_to_gcs.py
│   ├── 12_export_products_to_gcs.py
│   ├── 20_create_bq_dataset.py     # bootstrap glamira_raw + tables
│   ├── 21_load_gcs_to_bq.py        # manual loader (same routing as the CF)
│   ├── 30_data_profiling.py        # writes docs/data_profiling_report_*.md
│   └── 99_pipeline_runbook.py      # one-shot orchestrator
├── cloud_function/                 # production trigger
│   ├── main.py                     # entry point: trigger_bigquery_load
│   ├── routing.py                  # GCS path → BQ table (shared with manual loader)
│   ├── requirements.txt
│   ├── deploy.sh                   # gcloud functions deploy …
│   └── .gcloudignore
└── docs/
    └── data_profiling_report_*.md  # generated
```

---

## Prerequisites (one-time, mostly already done in Project 05)

| Component | What you need |
| --- | --- |
| GCP project | `unigap-de-glamira-data` |
| GCS bucket | `gs://unigap-prj5-raw` (region `asia-southeast1`) — **reused** |
| Service accounts | `sa-p05-vm-ingest@…` (attached to VM, owns `storage.objectAdmin` on the bucket); `sa-p05-bq-loader@…` (will run the Cloud Function) |
| APIs to enable for Project 06 | `bigquery.googleapis.com`, `cloudfunctions.googleapis.com`, `cloudbuild.googleapis.com`, `eventarc.googleapis.com`, `run.googleapis.com`, `pubsub.googleapis.com`, `artifactregistry.googleapis.com`, `logging.googleapis.com` |
| BigQuery dataset | `glamira_raw` in `asia-southeast1` (created by step 2 below) |

### One-time IAM grants

```bash
PROJECT=unigap-de-glamira-data
SA=sa-p05-bq-loader@${PROJECT}.iam.gserviceaccount.com

# CF can read objects from the lake bucket:
gcloud storage buckets add-iam-policy-binding gs://unigap-prj5-raw \
  --member="serviceAccount:${SA}" --role="roles/storage.objectViewer"

# CF can submit BigQuery load jobs and write to glamira_raw tables:
gcloud projects add-iam-policy-binding "${PROJECT}" \
  --member="serviceAccount:${SA}" --role="roles/bigquery.jobUser"

# (after dataset is created) grant write at the dataset level:
bq add-iam-policy-binding \
  --member="serviceAccount:${SA}" \
  --role="roles/bigquery.dataEditor" \
  ${PROJECT}:glamira_raw
```

### Eventarc service agent (one-time per project)

```bash
PROJECT_NUMBER=$(gcloud projects describe "${PROJECT}" --format='value(projectNumber)')
EVENTARC_SA="service-${PROJECT_NUMBER}@gcp-sa-eventarc.iam.gserviceaccount.com"

gcloud projects add-iam-policy-binding "${PROJECT}" \
  --member="serviceAccount:${EVENTARC_SA}" --role="roles/eventarc.eventReceiver"
```

> The Eventarc agent is created automatically the first time you call
> `gcloud functions deploy --gen2 --trigger-event-filters="…"`. If the deploy
> step fails with "missing eventReceiver", run the binding above and retry.

### GCS Pub/Sub publishing permission (one-time per project)

GCS uses the project-level Pub/Sub publisher SA to publish object-finalize
events; grant it once:

```bash
GCS_SA=$(gsutil kms serviceaccount -p "${PROJECT}")
gcloud projects add-iam-policy-binding "${PROJECT}" \
  --member="serviceAccount:${GCS_SA}" --role="roles/pubsub.publisher"
```

---

## Setup (on the VM `p05-mongo-vm`)

```bash
# 1. Pull repo + cd into Project6
cd ~/work/UNIGAP-DE/Project6

# 2. Create a virtualenv and install deps
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt

# 3. Create local .env from template, fill in MONGO_* secrets, INGEST_DATE…
cp .env.example .env
$EDITOR .env

# 4. Sanity check
python3 -c "from dotenv import load_dotenv; load_dotenv(); import os; \
print('GCP:', os.environ['GCP_PROJECT_ID'], 'bucket:', os.environ['GCS_BUCKET'])"
```

---

## Running the pipeline

### Step 1 — Bootstrap BigQuery dataset & tables (one-shot, idempotent)

```bash
python3 scripts/20_create_bq_dataset.py
```

Creates `glamira_raw` and three tables with the schemas in `schemas/*.json`,
ingestion-time partitioning, and the cluster keys defined in `ARCHITECTURE.md`.

Re-running this script is safe: existing tables get **schema additions** (no
data loss), the dataset is left alone if it already exists.

### Step 2 — Export raw events from MongoDB to GCS

This is the heaviest step; expect ~1–3 hours on the VM for 41M docs depending
on disk + network.

```bash
# Run inside tmux on the VM:
tmux new -s p06-events
. .venv/bin/activate
set -a && source .env && set +a
python3 scripts/10_export_events_to_gcs.py
# Ctrl-b d  to detach
```

What it produces on GCS:

```
gs://unigap-prj5-raw/raw/p06/events/ingest_date=2026-05-10/events_part-00000.ndjson.gz
gs://unigap-prj5-raw/raw/p06/events/ingest_date=2026-05-10/events_part-00001.ndjson.gz
...
```

The script is **resumable** — if SSH drops or the VM reboots mid-export, just
re-run the command with the same `INGEST_DATE`. Already-uploaded shards are
detected via `bucket.blob(...).exists()` and skipped.

### Step 3 — Re-package P05 CSVs and upload to the Project 06 prefix

```bash
python3 scripts/11_export_ip_locations_to_gcs.py
python3 scripts/12_export_products_to_gcs.py
```

These scripts find the original CSVs from Project 05 (`Project5/exports/...`
locally, or the same path on the VM) and upload a gzipped copy under
`raw/p06/{ip_locations,products}/ingest_date=…/`.

### Step 4 — Deploy the Cloud Function

```bash
cd cloud_function
set -a && source ../.env && set +a
bash deploy.sh
```

Verify the trigger:

```bash
gcloud eventarc triggers list --location="${GCP_REGION}" \
    --filter="name~${CF_NAME}" \
    --format="table(name,destination.cloudFunction,eventFilters)"
```

Tail logs:

```bash
gcloud functions logs read "${CF_NAME}" --gen2 --region="${GCP_REGION}" --limit=100
```

### Step 5 — Smoke test the trigger

Easiest smoke test: re-upload the small `products.csv.gz` (it has
`WRITE_TRUNCATE` so you don't pollute production data):

```bash
INGEST_DATE=$(date -u +%F-smoke) python3 scripts/12_export_products_to_gcs.py
gcloud functions logs read "${CF_NAME}" --gen2 --region="${GCP_REGION}" --limit=20
bq query --use_legacy_sql=false \
  "SELECT COUNT(*) FROM \`${GCP_PROJECT_ID}.${BQ_DATASET_RAW}.products\`"
```

You should see in CF logs something like:

```
received event id=… name=raw/p06/products/ingest_date=…/products.csv.gz
starting BQ load :: job_id=p06_load_… -> ${PROJECT}.glamira_raw.products
BQ load done :: rows_loaded=19417 …
```

### Step 6 — Run profiling & generate the report

```bash
python3 scripts/30_data_profiling.py
# -> writes docs/data_profiling_report_<INGEST_DATE>.md
```

The report covers (per the spec):

1. **Source overview** — table names, columns, types, modes, declared logical FKs.
2. **Null & distinct counts** per scalar column.
3. **Type consistency** — rows whose values fail `SAFE_CAST` to the declared type.
4. **Per-table KPIs** — `events` event-name distribution, `ip_locations`
   country distribution, `products` crawl success rate.

### Or — one-shot full pipeline

```bash
python3 scripts/99_pipeline_runbook.py
# or, after the Cloud Function is wired and you don't want the manual loader:
python3 scripts/99_pipeline_runbook.py --skip-load
```

---

## Verification queries (paste into BigQuery console)

```sql
-- Row counts per raw table
SELECT 'events' AS t, COUNT(*) AS n FROM `unigap-de-glamira-data.glamira_raw.events`
UNION ALL
SELECT 'ip_locations', COUNT(*) FROM `unigap-de-glamira-data.glamira_raw.ip_locations`
UNION ALL
SELECT 'products', COUNT(*) FROM `unigap-de-glamira-data.glamira_raw.products`;

-- Top 20 event types in the raw events table
SELECT COALESCE(event_name, collection) AS event_name, COUNT(*) AS n
FROM `unigap-de-glamira-data.glamira_raw.events`
GROUP BY 1
ORDER BY n DESC
LIMIT 20;

-- Logical-FK coverage: how many events have a matching IP in ip_locations?
SELECT
  COUNTIF(l.ip IS NOT NULL) / COUNT(*) AS ip_match_ratio
FROM `unigap-de-glamira-data.glamira_raw.events` e
LEFT JOIN `unigap-de-glamira-data.glamira_raw.ip_locations` l
USING (ip);
```

---

## Troubleshooting

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| CF deploy fails: `missing eventReceiver` | Eventarc agent missing role | Run the IAM binding in the Prerequisites section. |
| CF logs: `Permission denied: bigquery.jobs.create` | Loader SA missing `roles/bigquery.jobUser` | Run the IAM binding in the Prerequisites section. |
| CF logs: `Already Exists: Job …` | Eventarc retried after a successful load | This is **expected & idempotent** — the function treats Conflict as success. |
| Events export crashes after N hours | SSH/Mongo cursor timeout | Re-run the command; resumable mode skips finalised shards. Bump `EVENTS_BATCH_SIZE` if shards take too long. |
| `events` rows have unexpected columns | New top-level field appeared in MongoDB | The CF uses `ALLOW_FIELD_ADDITION` so BQ adds the column automatically. Update `schemas/events.json` to keep the explicit schema in sync. |
| Profiling fails on `events.cart_products` | JSON column profiling skipped | Expected — JSON / RECORD types are not SAFE_CAST-able. |

---

## Deliverables checklist (per Project 06 brief)

- [x] **Automated data pipeline**: `scripts/10–12_*.py` (extract+load to GCS) + Cloud Function (auto-load to BQ).
- [x] **Cloud Function triggers**: `cloud_function/` with Eventarc Gen 2 trigger on GCS object finalize.
- [x] **BigQuery tables**: `glamira_raw.{events, ip_locations, products}` with explicit schemas, partitioning & clustering.
- [x] **Data profiling**: `scripts/30_data_profiling.py` + `sql/profiling_*.sql` → `docs/data_profiling_report_*.md`.
- [x] **GitHub repository**: this folder, parallel to `Project5/`.
