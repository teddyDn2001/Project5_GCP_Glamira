#!/usr/bin/env python3
from __future__ import annotations

import csv
import os
import random
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from pymongo import MongoClient, ASCENDING, UpdateOne
from urllib.parse import quote_plus


PRODUCT_EVENTS = [
    "view_product_detail",
    "select_product_option",
    "select_product_option_quality",
    "add_to_cart_action",
    "product_detail_recommendation_visible",
    "product_detail_recommendation_noticed",
    "product_view_all_recommend_clicked",
]

USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0 Safari/537.36",
]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def clean_text(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip())


def extract_name(html: str) -> str | None:
    soup = BeautifulSoup(html, "lxml")

    og = soup.select_one('meta[property="og:title"]')
    if og and og.get("content"):
        t = clean_text(og["content"])
        if t:
            return t

    title = clean_text(soup.title.string if soup.title else "")
    if title:
        return title

    h1 = soup.find("h1")
    if h1:
        t = clean_text(h1.get_text(" "))
        if t:
            return t

    return None


@dataclass
class CrawlConfig:
    max_items: int
    sleep_min: float
    sleep_max: float
    timeout: float
    max_retries: int
    backoff_base: float


def fetch(url: str, cfg: CrawlConfig) -> tuple[int, str | None, str | None]:
    headers = {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9,fr;q=0.8",
        "Connection": "close",
    }

    for attempt in range(1, cfg.max_retries + 1):
        try:
            r = requests.get(url, headers=headers, timeout=cfg.timeout, allow_redirects=True)
            status = r.status_code

            if status in (429, 403, 503):
                wait = (cfg.backoff_base**attempt) + random.uniform(0, 1.0)
                return status, None, f"blocked_{status}_wait_{wait:.1f}s"

            if status >= 400:
                return status, None, f"http_{status}"

            name = extract_name(r.text)
            if not name:
                return status, None, "no_name_found"
            return status, name, None

        except requests.RequestException as e:
            if attempt == cfg.max_retries:
                return 0, None, f"request_error:{e.__class__.__name__}"
            wait = (cfg.backoff_base**attempt) + random.uniform(0, 1.0)
            time.sleep(wait)

    return 0, None, "unknown"


def mongo_client_from_env() -> MongoClient:
    host = os.getenv("MONGO_HOST", "127.0.0.1")
    port = int(os.getenv("MONGO_PORT", "27017"))
    admin_user = os.getenv("MONGO_ADMIN_USER", "")
    admin_pwd = os.getenv("MONGO_ADMIN_PWD", "")
    if not admin_user or not admin_pwd:
        raise RuntimeError("Missing MONGO_ADMIN_USER / MONGO_ADMIN_PWD. Load .env before running.")
    uri = f"mongodb://{quote_plus(admin_user)}:{quote_plus(admin_pwd)}@{host}:{port}/admin"
    return MongoClient(uri)


def build_product_events(client: MongoClient, raw_db: str, raw_coll: str, work_db: str) -> None:
    src = client[raw_db][raw_coll]
    dst = client[work_db]

    dst.product_events.drop()
    src.aggregate(
        [
            {"$addFields": {"event_name": "$collection"}},
            {"$match": {"event_name": {"$in": PRODUCT_EVENTS}}},
            {
                "$project": {
                    "time_stamp": 1,
                    "event_name": 1,
                    "product_id": 1,
                    "viewing_product_id": 1,
                    "current_url": 1,
                    "referrer_url": 1,
                    "device_id": 1,
                    "ip": 1,
                }
            },
            {"$out": {"db": work_db, "coll": "product_events"}},
        ],
        allowDiskUse=True,
    )

    dst.product_events.create_index([("event_name", ASCENDING)])
    dst.product_events.create_index([("time_stamp", -1)])
    dst.product_events.create_index([("product_id", ASCENDING)])
    dst.product_events.create_index([("viewing_product_id", ASCENDING)])


def build_product_candidates(client: MongoClient, work_db: str) -> None:
    src = client[work_db]["product_events"]
    dst = client[work_db]

    dst.product_candidates.drop()
    # Use $top to avoid sorting the entire dataset.
    src.aggregate(
        [
            {
                "$project": {
                    "time_stamp": 1,
                    "canonical_product_id": {"$ifNull": ["$product_id", "$viewing_product_id"]},
                    "best_url": {"$ifNull": ["$current_url", "$referrer_url"]},
                }
            },
            {"$match": {"canonical_product_id": {"$ne": None}, "best_url": {"$type": "string", "$ne": ""}}},
            {
                "$group": {
                    "_id": "$canonical_product_id",
                    "top": {
                        "$top": {
                            "sortBy": {"time_stamp": -1},
                            "output": {"best_url": "$best_url", "last_seen_ts": "$time_stamp"},
                        }
                    },
                }
            },
            {"$project": {"_id": 0, "product_id": "$_id", "best_url": "$top.best_url", "last_seen_ts": "$top.last_seen_ts"}},
            {"$out": {"db": work_db, "coll": "product_candidates"}},
        ],
        allowDiskUse=True,
    )
    dst.product_candidates.create_index([("product_id", ASCENDING)], unique=True)


def iter_candidates(coll, max_items: int) -> Iterable[dict]:
    cur = coll.find({}, {"product_id": 1, "best_url": 1, "last_seen_ts": 1}).sort("last_seen_ts", -1)
    n = 0
    for doc in cur:
        if max_items and n >= max_items:
            break
        yield doc
        n += 1


def crawl_and_store_products(client: MongoClient, work_db: str, cfg: CrawlConfig, run_date: str) -> Path:
    db = client[work_db]
    candidates = db.product_candidates
    products = db.products

    products.create_index([("product_id", ASCENDING)], unique=True)
    products.create_index([("status", ASCENDING)])
    products.create_index([("updated_at", ASCENDING)])

    already = set(products.distinct("product_id"))

    ops: list[UpdateOne] = []
    out_dir = Path("exports/products").resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"products_{run_date}.csv"

    with out_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["product_id", "product_name", "source_url", "status", "error", "updated_at"])
        w.writeheader()

        for doc in iter_candidates(candidates, cfg.max_items):
            pid = str(doc.get("product_id") or "").strip()
            url = doc.get("best_url")
            if not pid or not url or pid in already:
                continue

            time.sleep(random.uniform(cfg.sleep_min, cfg.sleep_max))

            status, name, err = fetch(url, cfg)
            rec = {
                "product_id": pid,
                "product_name": name,
                "source_url": url,
                "last_seen_ts": doc.get("last_seen_ts"),
                "status": status,
                "error": err,
                "updated_at": now_iso(),
                "run_date": run_date,
            }

            ops.append(UpdateOne({"product_id": pid}, {"$set": rec}, upsert=True))
            w.writerow(
                {
                    "product_id": pid,
                    "product_name": name or "",
                    "source_url": url,
                    "status": status,
                    "error": err or "",
                    "updated_at": rec["updated_at"],
                }
            )

            # batch flush
            if len(ops) >= 200:
                products.bulk_write(ops, ordered=False)
                ops.clear()

            # global slow-down when blocked
            if status in (429, 403, 503):
                time.sleep(10 + random.uniform(0, 5))

    if ops:
        products.bulk_write(ops, ordered=False)

    return out_path


def main() -> None:
    load_dotenv()

    raw_db = os.getenv("RAW_DB", "countly")
    raw_coll = os.getenv("RAW_COLL", "summary")
    work_db = os.getenv("WORK_DB", "glamira")
    run_date = os.getenv("RUN_DATE") or datetime.utcnow().strftime("%Y-%m-%d")

    cfg = CrawlConfig(
        max_items=int(os.getenv("MAX_ITEMS", "0")),
        sleep_min=float(os.getenv("SLEEP_MIN", "1.0")),
        sleep_max=float(os.getenv("SLEEP_MAX", "2.5")),
        timeout=float(os.getenv("REQUEST_TIMEOUT", "20")),
        max_retries=int(os.getenv("MAX_RETRIES", "6")),
        backoff_base=float(os.getenv("BACKOFF_BASE", "1.6")),
    )

    Path("logs").mkdir(exist_ok=True)
    log_path = Path("logs") / f"products_pipeline_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.log"

    # Simple file logger (no external deps)
    def log(msg: str) -> None:
        line = f"{datetime.utcnow().isoformat()} {msg}"
        print(line)
        log_path.open("a", encoding="utf-8").write(line + "\n")

    client = mongo_client_from_env()

    log("STEP build_product_events start")
    build_product_events(client, raw_db, raw_coll, work_db)
    log("STEP build_product_events done")

    log("STEP build_product_candidates start")
    build_product_candidates(client, work_db)
    log("STEP build_product_candidates done")

    log("STEP crawl_and_store_products start")
    csv_path = crawl_and_store_products(client, work_db, cfg, run_date)
    log(f"STEP crawl_and_store_products done csv={csv_path}")


if __name__ == "__main__":
    main()

