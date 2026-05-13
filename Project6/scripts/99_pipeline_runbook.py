#!/usr/bin/env python3
"""
End-to-end orchestrator for Project 06 (local / VM).

Steps (skip-able via flags):
  1. Bootstrap BigQuery dataset + tables (idempotent).
  2. Export raw events from MongoDB to GCS (NDJSON.gz).
  3. Re-package & upload IP2Location CSV to GCS.
  4. Re-package & upload Products CSV to GCS.
  5. Run the BigQuery loader (manual path) — this is normally done by the
     Cloud Function, but the runbook can drive it locally too (e.g. when
     the function is paused, or for the very first smoke test before the
     trigger is wired up).
  6. Run data profiling and emit the Markdown report.

Usage:
  python3 scripts/99_pipeline_runbook.py                       # full run
  python3 scripts/99_pipeline_runbook.py --skip-events         # don't dump 41M events
  python3 scripts/99_pipeline_runbook.py --skip-load           # rely on Cloud Function instead
  python3 scripts/99_pipeline_runbook.py --only profiling      # just rebuild the DQ report
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


STEPS = [
    ("bootstrap",   "20_create_bq_dataset.py"),
    ("events",      "10_export_events_to_gcs.py"),
    ("ip",          "11_export_ip_locations_to_gcs.py"),
    ("products",    "12_export_products_to_gcs.py"),
    ("load",        "21_load_gcs_to_bq.py"),
    ("profiling",   "30_data_profiling.py"),
]


def run(script: str) -> None:
    print(f"\n$ python3 {script}")
    subprocess.check_call(["python3", str(SCRIPTS / script)], cwd=str(ROOT), env=os.environ.copy())


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--skip-bootstrap", action="store_true")
    ap.add_argument("--skip-events", action="store_true")
    ap.add_argument("--skip-ip", action="store_true")
    ap.add_argument("--skip-products", action="store_true")
    ap.add_argument("--skip-load", action="store_true",
                    help="Skip the manual loader (use this when the Cloud Function is wired up).")
    ap.add_argument("--skip-profiling", action="store_true")
    ap.add_argument(
        "--only",
        choices=[s for s, _ in STEPS],
        help="Run only this single step (overrides --skip-* flags).",
    )
    args = ap.parse_args()

    if args.only:
        for name, script in STEPS:
            if name == args.only:
                run(script)
                return
        return

    skip = {
        "bootstrap":  args.skip_bootstrap,
        "events":     args.skip_events,
        "ip":         args.skip_ip,
        "products":   args.skip_products,
        "load":       args.skip_load,
        "profiling":  args.skip_profiling,
    }

    for name, script in STEPS:
        if skip[name]:
            print(f"[runbook] SKIP {name} ({script})")
            continue
        run(script)

    print("\n[runbook] DONE — see logs/ and docs/data_profiling_report_*.md")


if __name__ == "__main__":
    main()
