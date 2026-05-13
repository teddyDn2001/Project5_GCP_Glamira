# UNIGAP DE — Glamira Data Engineering on GCP

End-to-end data engineering portfolio for the **Glamira** analytics dataset, built incrementally across multiple projects. Each project lives in its own folder and is **self-contained** (its own `README.md`, `.env.example`, `requirements.txt`, scripts).

| Project | Folder | Focus | Status |
| --- | --- | --- | --- |
| **Project 5** | [`Project5/`](./Project5/) | **Data Collection & Storage Foundation** — GCS lake, VM + MongoDB, IP enrichment, product crawling | ✅ done |
| **Project 6** | [`Project6/`](./Project6/) | **Automated Data Pipeline** — Export raw events to GCS, Cloud Function (Gen 2) trigger, BigQuery raw layer, data profiling | ✅ done |
| **Project 7** | _(coming)_ | **dbt Transformations** — staging → marts on top of the raw layer | 🛠 planned |

```
┌────────────────┐    ┌──────────────────┐    ┌──────────────────┐    ┌────────────────────┐    ┌──────────┐
│  MongoDB (VM)  │    │ Google Cloud     │    │ Cloud Function   │    │ BigQuery           │    │ Looker   │
│  Project 5     │ ─► │ Storage (lake)   │ ─► │ (Eventarc Gen 2) │ ─► │ glamira_raw → dbt  │ ─► │ Project 8│
│                │    │ Project 5 + 6    │    │ Project 6        │    │ Project 7          │    │          │
└────────────────┘    └──────────────────┘    └──────────────────┘    └────────────────────┘    └──────────┘
```

---

## Common context (shared across projects)

- **GCP project**: `unigap-de-glamira-data` (region `asia-southeast1`)
- **GCS bucket (lake)**: `gs://unigap-prj5-raw`
  - Project 5 prefixes: `raw/glamira/ingest_date=…/`, `exports/{ip_locations,products}/run_date=…/`
  - Project 6 prefixes: `raw/p06/{events,ip_locations,products}/ingest_date=…/`
- **VM**: `p05-mongo-vm` (MongoDB bound to localhost, auth enabled)
- **Service accounts**:
  - `sa-p05-vm-ingest@…` — attached to the VM, writes to the lake.
  - `sa-p05-bq-loader@…` — runs the Cloud Function, loads GCS → BigQuery.

Secrets (Mongo passwords, etc.) are kept in each project's own `.env` (gitignored). Templates live in `*/​.env.example`.

---

## Quick start

Each project has its own runbook. Start with the one you want to reproduce:

- Project 5 — see [`Project5/README.md`](./Project5/README.md) for VM setup, MongoDB restore, IP/products pipeline.
- Project 6 — see [`Project6/README.md`](./Project6/README.md) for the GCS → BigQuery automated pipeline, or [`Project6/docs/LEARNING_GUIDE.md`](./Project6/docs/LEARNING_GUIDE.md) for a step-by-step walkthrough of the problem.

---

## Repo conventions

- One folder per project, **never** spill files into the repo root.
- Per-project `.env.example` — copy to `.env` locally, never commit.
- Per-project `requirements.txt` so each project can be installed in isolation.
- `LESSONS_LEARNED.md` / `ARCHITECTURE.md` next to the code, not in a separate wiki.
- Commits use Conventional-Commits-ish prefixes: `feat:`, `fix:`, `docs:`, `chore:`.
