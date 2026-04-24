#!/usr/bin/env python3
from __future__ import annotations

import csv
import os
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from pymongo import MongoClient, ASCENDING


def mongo_client_from_env() -> MongoClient:
    host = os.getenv("MONGO_HOST", "127.0.0.1")
    port = int(os.getenv("MONGO_PORT", "27017"))
    admin_user = os.getenv("MONGO_ADMIN_USER", "")
    admin_pwd = os.getenv("MONGO_ADMIN_PWD", "")
    if not admin_user or not admin_pwd:
        raise RuntimeError("Missing MONGO_ADMIN_USER / MONGO_ADMIN_PWD. Load .env before running.")
    uri = f"mongodb://{admin_user}:{admin_pwd}@{host}:{port}/admin"
    return MongoClient(uri)


def main() -> None:
    load_dotenv()

    raw_db = os.getenv("RAW_DB", "countly")
    raw_coll = os.getenv("RAW_COLL", "summary")
    work_db = os.getenv("WORK_DB", "glamira")
    run_date = os.getenv("RUN_DATE") or datetime.utcnow().strftime("%Y-%m-%d")

    export_csv = os.getenv("EXPORT_UNIQUE_IPS_CSV", "1") == "1"
    out_dir = Path(os.getenv("OUT_DIR", "exports/ip_locations")).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"unique_ips_{run_date}.csv"

    client = mongo_client_from_env()
    src = client[raw_db][raw_coll]
    dst = client[work_db]["unique_ips"]

    # Build collection via $out (fast & deterministic)
    pipeline = [
        {"$match": {"ip": {"$type": "string", "$ne": ""}}},
        {"$group": {"_id": "$ip"}},
        {"$project": {"_id": 0, "ip": "$_id"}},
        {"$out": {"db": work_db, "coll": "unique_ips"}},
    ]
    src.aggregate(pipeline, allowDiskUse=True)

    # Enforce uniqueness
    dst.create_index([("ip", ASCENDING)], unique=True)

    count = dst.estimated_document_count()
    print(f"unique_ips count: {count}")

    if export_csv:
        with out_path.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["ip"])
            w.writeheader()
            for doc in dst.find({}, {"_id": 0, "ip": 1}):
                w.writerow({"ip": doc.get("ip")})
        print(f"Wrote CSV: {out_path}")


if __name__ == "__main__":
    main()

