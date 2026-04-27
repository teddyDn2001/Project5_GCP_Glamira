# Project 05 — Senior-ready checklist & lessons learned

## Senior-ready submission checklist

- **Architecture**: Raw on GCS (immutable) + processing store on VM MongoDB + derived exports for downstream use.
- **Prefixing / partitions**: Use audit-friendly paths:
  - Raw: `raw/<domain>/ingest_date=YYYY-MM-DD/`
  - Exports: `exports/<dataset>/run_date=YYYY-MM-DD/`
- **Immutability**: Never overwrite raw dumps; new ingest = new `ingest_date` prefix.
- **Reproducibility**: Same inputs + `.env` config + scripts ⇒ deterministic collections/exports.
- **Idempotency**: Safe re-runs via `$out/$merge`, `unique` indexes, and `upsert` patterns.
- **Resumability**: Long jobs resume by skipping already-processed keys (e.g., `ip`, `product_id`) rather than restarting from scratch.
- **Data modeling for pipelines**: Build “dimensions” first (e.g., `unique_ips`, `product_candidates`) to reduce repeated work and enable joins/enrichment.
- **Data quality checks**: Validate counts at each stage (e.g., `unique_ips == ip_locations`, `product_candidates == products`) and spot-check sample records.
- **Operational observability**: Keep logs per run, track step boundaries, and verify progress via counts/exports (not only console output).
- **Crawling robustness**: Handle real-world HTTP failures (403/429/503), retries, backoff, and sleep jitter to reduce blocking.
- **Security (least privilege)**: Avoid `roles/editor`; grant viewer/objectViewer/osLogin only as needed.
- **Security (host hardening)**: SSH key-only, no root login, no password auth; MongoDB bound to localhost with authorization enabled.
- **Secrets hygiene**: No secrets in git; use `.env` on VM/local and keep `.env.example` in repo.
- **Cost awareness**: Stop VM when jobs finish; persistent disk and storage still cost money—clean up unused artifacts and avoid duplicate large uploads.
- **Evidence for submission**: Provide GCS artifact paths + final collection counts + brief explanation of limitations (e.g., some crawls blocked but 1 record per key enforced).

## Lessons learned (senior tone)

- Designed an audit-friendly lakehouse-style foundation: immutable raw on GCS, operational processing on MongoDB, and reproducible exports for downstream transformation.
- Prioritized idempotency and resumability so long-running enrichment/crawling jobs can be re-run safely and recover from SSH/network drops.
- Applied defense-in-depth: least-privilege IAM, hardened SSH access, and local-only MongoDB exposure with authorization enabled; secrets kept out of version control.
- Treated web crawling as an unreliable dependency and implemented retry/backoff/sleep jitter to operate within rate limits and anti-bot constraints.
- Validated pipeline correctness with stage-by-stage counts, unique indexes, and final parity checks to ensure “one record per key” guarantees.
- Managed cost by separating compute-heavy steps from storage, uploading only necessary artifacts, and stopping compute resources when processing completes.

