#!/usr/bin/env python3
"""
Run a *Data Profiling* pass against the BigQuery raw layer and emit a
human-readable Markdown report at:

    docs/data_profiling_report_${INGEST_DATE}.md

What it covers (per the Project 06 spec):

    1. Information about the data sources
       - table names, column names, data types, modes (NULLABLE/REQUIRED)
       - relationships (declared in this script's KNOWN_JOINS dict)
    2. Null counts + distinct value counts per column
    3. Data type consistency — confirms each column's declared type by
       running TYPEOF-style probes (e.g. SAFE_CAST → BOOL).
    4. Per-table profiling SQL (see sql/profiling_*.sql) for top-level KPIs.

Why one script (and not three)?
    Because the report is meant to live next to the code as a single
    deliverable. Splitting it would force the reviewer to chase three files.

Run:
    python3 scripts/30_data_profiling.py
"""

from __future__ import annotations

import sys
from pathlib import Path
from string import Template
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from dotenv import load_dotenv
from google.cloud import bigquery

from _common import configure_logging, env, ingest_date


PROFILE_TABLES = ["events", "ip_locations", "products"]

# Foreign-key-style relationships (no real FK in BQ, but documenting intent).
KNOWN_JOINS = [
    ("events.product_id", "products.product_id"),
    ("events.ip", "ip_locations.ip"),
]

SQL_DIR = Path(__file__).resolve().parents[1] / "sql"


def render_sql(filename: str, project: str, dataset: str) -> str:
    template = Template((SQL_DIR / filename).read_text(encoding="utf-8"))
    return template.substitute(project=project, dataset=dataset)


def md_table(headers: list[str], rows: list[list[Any]]) -> str:
    """Tiny Markdown table renderer (no extra dep)."""
    out = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    for row in rows:
        out.append("| " + " | ".join("" if v is None else str(v) for v in row) + " |")
    return "\n".join(out)


def schema_section(client: bigquery.Client, project: str, dataset: str, table: str) -> str:
    tbl = client.get_table(f"{project}.{dataset}.{table}")
    rows = [
        [f.name, f.field_type, f.mode, (f.description or "").replace("\n", " ")[:120]]
        for f in tbl.schema
    ]
    info = (
        f"- **Full id**: `{tbl.full_table_id}`\n"
        f"- **Partitioning**: `{tbl.time_partitioning}`\n"
        f"- **Clustering fields**: `{tbl.clustering_fields}`\n"
        f"- **Row count (estimated)**: `{tbl.num_rows:,}`\n"
        f"- **Size**: `{tbl.num_bytes/1e6:.2f} MB`\n"
    )
    return info + "\n" + md_table(["column", "type", "mode", "description"], rows)


def null_distinct_query(project: str, dataset: str, table: str, columns: list[str]) -> str:
    """Build one query that returns null_count + approx distinct per column."""
    parts = []
    for col in columns:
        parts.append(
            f"  COUNTIF(`{col}` IS NULL) AS null_count_{_safe(col)},\n"
            f"  APPROX_COUNT_DISTINCT(`{col}`) AS distinct_count_{_safe(col)}"
        )
    select = ",\n".join(parts)
    return f"SELECT\n{select}\nFROM `{project}.{dataset}.{table}`"


def _safe(name: str) -> str:
    return "".join(c if c.isalnum() else "_" for c in name)


def null_distinct_section(client: bigquery.Client, project: str, dataset: str, table: str) -> str:
    tbl = client.get_table(f"{project}.{dataset}.{table}")
    # Skip JSON columns from null/distinct (cheaper + APPROX_COUNT_DISTINCT doesn't apply).
    cols = [f.name for f in tbl.schema if f.field_type != "JSON"]
    if not cols:
        return "_(no scalar columns to profile)_"

    sql = null_distinct_query(project, dataset, table, cols)
    row = list(client.query(sql).result())[0]
    out_rows = []
    for col in cols:
        out_rows.append([
            col,
            row[f"null_count_{_safe(col)}"],
            row[f"distinct_count_{_safe(col)}"],
        ])
    return md_table(["column", "null_count", "approx_distinct"], out_rows)


def type_consistency_section(client: bigquery.Client, project: str, dataset: str, table: str) -> str:
    """For each column, count rows whose value can NOT SAFE_CAST to its declared type.

    SAFE_CAST returns NULL on failure; subtracting the legitimate NULL count
    (rows where the column was NULL to begin with) tells us how many rows
    failed type coercion.
    """
    tbl = client.get_table(f"{project}.{dataset}.{table}")
    rows: list[list[Any]] = []
    for f in tbl.schema:
        # Skip JSON / RECORD types — SAFE_CAST is not meaningful for them.
        if f.field_type in ("JSON", "RECORD", "STRUCT"):
            rows.append([f.name, f.field_type, "skipped (semi-structured)"])
            continue
        target_type = f.field_type if f.field_type != "FLOAT" else "FLOAT64"
        sql = (
            f"SELECT "
            f"COUNTIF(`{f.name}` IS NOT NULL AND SAFE_CAST(CAST(`{f.name}` AS STRING) AS {target_type}) IS NULL) "
            f"AS bad FROM `{project}.{dataset}.{table}`"
        )
        bad = list(client.query(sql).result())[0]["bad"]
        rows.append([f.name, f.field_type, bad])
    return md_table(["column", "declared_type", "rows_failing_cast"], rows)


def per_table_sql_section(client: bigquery.Client, project: str, dataset: str, table: str) -> str:
    sql = render_sql(f"profiling_{table}.sql", project, dataset)
    job = client.query(sql)
    rows = [[r["metric"], r["value"]] for r in job.result()]
    return md_table(["metric", "value"], rows)


def main() -> None:
    load_dotenv()
    log = configure_logging("data_profiling")

    project = env("GCP_PROJECT_ID", required=True)
    dataset = env("BQ_DATASET_RAW", "glamira_raw")
    location = env("BQ_LOCATION", "asia-southeast1")

    client = bigquery.Client(project=project, location=location)

    out_path = Path("docs") / f"data_profiling_report_{ingest_date()}.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    sections: list[str] = []
    sections.append(f"# Data Profiling Report — {project}.{dataset}")
    sections.append(f"_Generated automatically by `scripts/30_data_profiling.py` for ingest_date `{ingest_date()}`._\n")

    sections.append("## 0. Source overview\n")
    sections.append(
        "| dataset | table | source on GCS |\n"
        "| --- | --- | --- |\n"
        f"| {dataset} | events | `gs://{env('GCS_BUCKET','?')}/{env('GCS_PREFIX_EVENTS','?')}/ingest_date=*/events_part-*.ndjson.gz` |\n"
        f"| {dataset} | ip_locations | `gs://{env('GCS_BUCKET','?')}/{env('GCS_PREFIX_IP_LOCATIONS','?')}/ingest_date=*/ip_locations.csv.gz` |\n"
        f"| {dataset} | products | `gs://{env('GCS_BUCKET','?')}/{env('GCS_PREFIX_PRODUCTS','?')}/ingest_date=*/products.csv.gz` |\n"
    )

    sections.append("### Documented relationships (logical FKs)\n")
    sections.append(
        "\n".join(f"- `{a}` → `{b}`" for a, b in KNOWN_JOINS)
    )

    for table in PROFILE_TABLES:
        log.info("profiling table=%s", table)
        sections.append(f"\n---\n\n## {table}\n")

        sections.append("### Schema\n")
        sections.append(schema_section(client, project, dataset, table))

        sections.append("\n### Null & distinct counts\n")
        sections.append(null_distinct_section(client, project, dataset, table))

        sections.append("\n### Type-consistency check\n")
        sections.append(
            "_Counts rows whose non-null value fails `SAFE_CAST` to its declared type._\n"
        )
        sections.append(type_consistency_section(client, project, dataset, table))

        sections.append("\n### Per-table KPIs\n")
        sections.append(per_table_sql_section(client, project, dataset, table))

    out_path.write_text("\n".join(sections) + "\n", encoding="utf-8")
    log.info("wrote %s", out_path)


if __name__ == "__main__":
    main()
