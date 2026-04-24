# Project 05 — Data Collection & Storage Foundation (GCP + MongoDB)

This folder contains the **local source code** (scripts + docs) used to implement Project 05 in a production-like way:

- **GCS** as the *raw* data lake (audit-friendly prefixes)
- **VM + MongoDB** as operational storage and processing engine
- Derived collections for:
  - **IP enrichment** (`unique_ips` → `ip_locations`)
  - **Product discovery + crawling** (`product_events` → `product_candidates` → `products`)

> Secrets must NOT be committed. Use `.env` locally/VM and keep `.env.example` in git.

---

## Repository inputs

- `dump/countly/summary.bson` + `summary.metadata.json`  
  MongoDB dump of `countly.summary` with indexes in metadata.
- `IP-COUNTRY-REGION-CITY.BIN`  
  IP2Location database used for IP geolocation.
- `README_Day1-3_Setup.md`  
  Setup notes for Day 1–3 (IAM/GCS/VM hardening).

---

## Setup (VM or local)

### 1) Create `.env`

```bash
cp .env.example .env
```

Fill in `MONGO_*` variables for your VM MongoDB and (optionally) `GCS_BUCKET`, `INGEST_DATE`, `RUN_DATE`.

### 2) Install dependencies

```bash
python3 -m pip install -r requirements.txt
```

---

## Scripts (runbook)

All scripts live in `scripts/` and are designed to be:

- **idempotent / resumable** (safe to rerun)
- **logged** (you can attach logs to submission)
- **least-privilege friendly** (app user for pipelines; admin only when required)

### A) Restore dump into MongoDB (raw)

1. Upload raw dump to GCS (optional).
2. Download to VM.
3. Restore into MongoDB:

```bash
python3 scripts/01_restore_dump.py \
  --dump-root dump \
  --db countly \
  --collection summary
```

### B) Build `unique_ips` for IP enrichment

```bash
python3 scripts/02_build_unique_ips.py
```

Outputs:
- MongoDB: `glamira.unique_ips` with `unique(ip)` index
- CSV export: `exports/ip_locations/unique_ips_<run_date>.csv` (optional)

### C) Enrich IP locations (`unique_ips` → `ip_locations`)

```bash
python3 scripts/04_enrich_ip_locations.py
```

Outputs:
- MongoDB: `glamira.ip_locations`
- CSV export: `exports/ip_locations/ip_locations_<run_date>.csv`

### D) Build product candidates and crawl product names

```bash
python3 scripts/03_products_pipeline.py
```

Outputs:
- MongoDB: `glamira.product_events`, `glamira.product_candidates`, `glamira.products`
- Logs: `logs/`
- CSV export: `exports/products/products_<run_date>.csv`

---

## End-to-end (one command)

Once `.env` is configured and dependencies are installed:

```bash
python3 scripts/00_end_to_end.py --restore-drop
```

Flags:
- `--skip-restore`: do not run `mongorestore` (useful if you already restored)
- `--restore-drop`: drop raw collection before restore (safe for clean reruns)

---

## Notes / best practices

- **Raw is immutable**: never overwrite raw dumps; use new `ingest_date=...` prefixes.
- For long-running commands, use `tmux` on the VM.
- Crawling can hit rate limits; the crawler implements retries + backoff + sleep jitter.

