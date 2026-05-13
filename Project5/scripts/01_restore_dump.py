#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import subprocess
from pathlib import Path


def sh(cmd: list[str]) -> None:
    print("\n$ " + " ".join(cmd))
    subprocess.check_call(cmd)


def main() -> None:
    ap = argparse.ArgumentParser(description="Restore mongodump-style BSON into MongoDB with metadata indexes.")
    ap.add_argument("--dump-root", default="dump", help="Dump root directory (contains <db>/<collection>.bson)")
    ap.add_argument("--db", required=True, help="Database name inside dump root, e.g. countly")
    ap.add_argument("--collection", required=True, help="Collection name, e.g. summary")
    ap.add_argument("--drop", action="store_true", help="Drop collection before restore")
    ap.add_argument("--workers", type=int, default=4, help="Insertion workers per collection")
    args = ap.parse_args()

    dump_root = Path(args.dump_root).resolve()
    bson_path = dump_root / args.db / f"{args.collection}.bson"
    meta_path = dump_root / args.db / f"{args.collection}.metadata.json"

    if not bson_path.exists():
        raise SystemExit(f"Missing BSON: {bson_path}")
    if not meta_path.exists():
        raise SystemExit(f"Missing metadata JSON: {meta_path}")

    # Rely on mongorestore for correct restore + indexes from metadata.
    # MongoDB auth is taken from environment variables to avoid committing secrets.
    admin_user = os.environ.get("MONGO_ADMIN_USER", "")
    admin_pwd = os.environ.get("MONGO_ADMIN_PWD", "")
    host = os.environ.get("MONGO_HOST", "127.0.0.1")
    port = os.environ.get("MONGO_PORT", "27017")

    if not admin_user or not admin_pwd:
        raise SystemExit("Missing MONGO_ADMIN_USER / MONGO_ADMIN_PWD in environment (load .env before running).")

    cmd = [
        "mongorestore",
        "--host",
        host,
        "--port",
        str(port),
        "-u",
        admin_user,
        "-p",
        admin_pwd,
        "--authenticationDatabase",
        "admin",
        "--numInsertionWorkersPerCollection",
        str(args.workers),
        "--nsInclude",
        f"{args.db}.{args.collection}",
        "--dir",
        str(dump_root),
    ]
    if args.drop:
        cmd.insert(cmd.index("--numInsertionWorkersPerCollection"), "--drop")

    sh(cmd)

    print("\nRestore completed. Recommended verify:")
    print(
        f"  mongosh -u \"$MONGO_ADMIN_USER\" -p \"$MONGO_ADMIN_PWD\" --authenticationDatabase admin "
        f"--eval 'db.getSiblingDB(\"{args.db}\").{args.collection}.estimatedDocumentCount()'"
    )


if __name__ == "__main__":
    main()

