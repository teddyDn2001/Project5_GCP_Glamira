# Glamira dbt — Project 07

Transform P6 raw (`glamira_raw`) → staging → mart star schema.

**Model (approved):** `fact_sales_order_detail` + `dim_date`, `dim_customer`, `dim_product`, `dim_location`; `is_paypal` on fact; no IP on dim.

## Prerequisites

- Python 3.10+
- `glamira_raw` loaded (P6): `events`, `products`, `ip_locations`
- GCP auth: `gcloud auth application-default login`

## Setup (Cloud Shell or laptop)

```bash
cd Project7/glamira_dbt

python3 -m venv .venv
source .venv/bin/activate
pip install dbt-bigquery

mkdir -p ~/.dbt
cp profiles.yml.example ~/.dbt/profiles.yml

dbt deps
dbt debug
```

## Run

```bash
# Build staging views
dbt run --select staging

# Check checkout row count
dbt show --inline "SELECT COUNT(*) n FROM {{ ref('stg_events__checkout_success') }}"

# Build mart (dims first, then fact)
dbt run --select mart

# Tests
dbt test
```

## Explore cart_products (optional line-item unnest)

```bash
# Paste analyses/explore_cart_products.sql in BigQuery Console
```

Then update `models/staging/stg_checkout_line_items.sql`.

## Datasets created

| dbt path | BigQuery dataset |
|----------|------------------|
| `models/staging/*` | `glamira_staging` (`dataset: glamira` + `+schema: staging`) |
| `models/mart/*` | `glamira_mart` (`dataset: glamira` + `+schema: mart`) |

**profiles.yml:** `dataset: glamira` (not `glamira_staging` — avoids `glamira_staging_glamira_staging`).

## Next steps (P7 checklist)

- [ ] `dbt run` + `dbt test` pass
- [ ] PII: Looker view with `SHA256(email_address)` for BI
- [ ] Looker: 4 dashboards on `glamira_mart`
- [ ] `dbt docs generate` → lineage for report
