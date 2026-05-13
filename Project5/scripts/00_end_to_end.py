#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import subprocess
from pathlib import Path


def run(cmd: list[str], cwd: Path) -> None:
    print("\n$ " + " ".join(cmd))
    subprocess.check_call(cmd, cwd=str(cwd), env=os.environ.copy())


def main() -> None:
    ap = argparse.ArgumentParser(description="Run Project5 end-to-end pipeline (local repo scripts).")
    ap.add_argument("--skip-restore", action="store_true", help="Skip mongorestore step")
    ap.add_argument("--restore-drop", action="store_true", help="Drop collection before restore")
    ap.add_argument("--dump-root", default="dump", help="Dump root directory (mongodump structure)")
    ap.add_argument("--raw-db", default=None, help="Override RAW_DB (default from env)")
    ap.add_argument("--raw-coll", default=None, help="Override RAW_COLL (default from env)")
    args = ap.parse_args()

    root = Path(__file__).resolve().parents[1]  # Project5/
    scripts = root / "scripts"

    if args.raw_db:
        os.environ["RAW_DB"] = args.raw_db
    if args.raw_coll:
        os.environ["RAW_COLL"] = args.raw_coll

    # 0) Restore raw dump (optional)
    if not args.skip_restore:
        cmd = [
            "python3",
            str(scripts / "01_restore_dump.py"),
            "--dump-root",
            args.dump_root,
            "--db",
            os.environ.get("RAW_DB", "countly"),
            "--collection",
            os.environ.get("RAW_COLL", "summary"),
        ]
        if args.restore_drop:
            cmd.append("--drop")
        run(cmd, cwd=root)

    # 1) unique IPs
    run(["python3", str(scripts / "02_build_unique_ips.py")], cwd=root)

    # 2) enrich IP locations
    run(["python3", str(scripts / "04_enrich_ip_locations.py")], cwd=root)

    # 3) products pipeline (events -> candidates -> crawl)
    run(["python3", str(scripts / "03_products_pipeline.py")], cwd=root)

    print("\nDONE. Outputs:")
    print(f"- {root / 'exports'}")
    print(f"- {root / 'logs'}")


if __name__ == "__main__":
    main()

