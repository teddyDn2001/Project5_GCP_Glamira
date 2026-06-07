# Project 07 — Data Transformation & Visualization (Glamira)

Builds on **Project 6** raw layer (`glamira_raw`).

## dbt project (implementation)

```bash
cd glamira_dbt
# see glamira_dbt/README.md
dbt deps && dbt run && dbt test
```

## Data model (for supervisor review)

| Document | Purpose |
|----------|---------|
| [`docs/DATA_MODEL.md`](docs/DATA_MODEL.md) | Full star schema, column dictionary, Mermaid diagrams |
| [`docs/glamira_mart.dbml`](docs/glamira_mart.dbml) | Import to [dbdiagram.io](https://dbdiagram.io) → export PNG/PDF |
| [`docs/glamira_drawsql_schema.sql`](docs/glamira_drawsql_schema.sql) | Import to [drawSQL](https://drawsql.app) — **PostgreSQL DDL** |
| [`docs/DRAWSQL_SETUP.md`](docs/DRAWSQL_SETUP.md) | Step-by-step drawSQL import / optional Postgres |
| [`docs/LOOKER_STUDIO_SETUP.md`](docs/LOOKER_STUDIO_SETUP.md) | Sale Performance Dashboard (Looker Studio + `vw_sales_performance`) |

## Quick send checklist

1. Export PNG from dbdiagram.io or Mermaid Live.
2. Attach `DATA_MODEL.md` (PDF export optional).
3. One-line summary: *Transaction fact `fact_sales_order_detail` from `checkout_success`, 5 dimensions, Looker on `glamira_mart`.*
