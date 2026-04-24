#!/usr/bin/env python3
from __future__ import annotations

import csv
import os
import time
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from pymongo import MongoClient, ASCENDING, UpdateOne
from urllib.parse import quote_plus

try:
    # Most installations expose the module with this casing.
    from IP2Location import IP2Location  # type: ignore
except Exception:  # pragma: no cover
    # Fallback for alternative module naming.
    from ip2location import IP2Location  # type: ignore


def mongo_client_from_env() -> MongoClient:
    host = os.getenv("MONGO_HOST", "127.0.0.1")
    port = int(os.getenv("MONGO_PORT", "27017"))
    admin_user = os.getenv("MONGO_ADMIN_USER", "")
    admin_pwd = os.getenv("MONGO_ADMIN_PWD", "")
    if not admin_user or not admin_pwd:
        raise RuntimeError("Missing MONGO_ADMIN_USER / MONGO_ADMIN_PWD. Load .env before running.")
    uri = f"mongodb://{quote_plus(admin_user)}:{quote_plus(admin_pwd)}@{host}:{port}/admin"
    return MongoClient(uri)


def main() -> None:
    load_dotenv()

    work_db = os.getenv("WORK_DB", "glamira")
    run_date = os.getenv("RUN_DATE") or datetime.utcnow().strftime("%Y-%m-%d")

    # input collection produced by scripts/02_build_unique_ips.py
    src_coll = os.getenv("UNIQUE_IPS_COLL", "unique_ips")
    dst_coll = os.getenv("IP_LOCATIONS_COLL", "ip_locations")

    bin_path = os.getenv("IP2LOCATION_BIN", "IP-COUNTRY-REGION-CITY.BIN")
    bin_file = Path(bin_path).expanduser().resolve()
    if not bin_file.exists():
        raise SystemExit(
            f"Missing IP2Location BIN file: {bin_file}\n"
            f"Set IP2LOCATION_BIN in .env or put the BIN in Project5/."
        )

    max_items = int(os.getenv("MAX_IPS", "0"))  # 0 = all
    sleep_ms = int(os.getenv("IP_LOOKUP_SLEEP_MS", "0"))

    export_csv = os.getenv("EXPORT_IP_LOCATIONS_CSV", "1") == "1"
    out_dir = Path(os.getenv("OUT_DIR_IP", "exports/ip_locations")).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"ip_locations_{run_date}.csv"

    client = mongo_client_from_env()
    src = client[work_db][src_coll]
    dst = client[work_db][dst_coll]

    dst.create_index([("ip", ASCENDING)], unique=True)
    dst.create_index([("country_short", ASCENDING)])
    dst.create_index([("updated_at", ASCENDING)])

    ipdb = IP2Location(str(bin_file))

    # Resume: skip already enriched IPs
    already = set(dst.distinct("ip"))

    ops: list[UpdateOne] = []
    processed = 0
    written = 0

    def flush() -> None:
        nonlocal written
        if ops:
            res = dst.bulk_write(ops, ordered=False)
            written += res.upserted_count + res.modified_count
            ops.clear()

    if export_csv:
        csv_f = out_path.open("w", newline="", encoding="utf-8")
        writer = csv.DictWriter(
            csv_f,
            fieldnames=[
                "ip",
                "country_short",
                "country_long",
                "region",
                "city",
                "latitude",
                "longitude",
                "zipcode",
                "timezone",
                "updated_at",
            ],
        )
        writer.writeheader()
    else:
        csv_f = None
        writer = None

    try:
        cur = src.find({}, {"_id": 0, "ip": 1})
        for doc in cur:
            ip = (doc.get("ip") or "").strip()
            if not ip:
                continue
            if ip in already:
                continue

            processed += 1
            if max_items and processed > max_items:
                break

            if sleep_ms:
                time.sleep(sleep_ms / 1000.0)

            rec = ipdb.get_all(ip)
            updated_at = datetime.utcnow().isoformat()

            row = {
                "ip": ip,
                "country_short": getattr(rec, "country_short", None),
                "country_long": getattr(rec, "country_long", None),
                "region": getattr(rec, "region", None),
                "city": getattr(rec, "city", None),
                "latitude": getattr(rec, "latitude", None),
                "longitude": getattr(rec, "longitude", None),
                "zipcode": getattr(rec, "zipcode", None),
                "timezone": getattr(rec, "timezone", None),
                "updated_at": updated_at,
            }

            ops.append(UpdateOne({"ip": ip}, {"$set": row}, upsert=True))
            if writer:
                writer.writerow(row)

            if len(ops) >= 1000:
                flush()

        flush()
    finally:
        if csv_f:
            csv_f.close()

    print(f"Processed unique IPs: {processed}")
    print(f"Mongo writes (approx): {written}")
    if export_csv:
        print(f"Wrote CSV: {out_path}")


if __name__ == "__main__":
    main()

