"""Shared helpers for Project 06 scripts.

Kept deliberately small so individual scripts stay self-contained and easy to read.
"""

from __future__ import annotations

import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote_plus


def configure_logging(name: str) -> logging.Logger:
    """File + stdout logger; one file per script per run."""
    log_dir = Path(os.getenv("LOG_DIR", "logs")).resolve()
    log_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    log_path = log_dir / f"{name}_{stamp}.log"

    fmt = "%(asctime)s %(levelname)s %(name)s :: %(message)s"
    handlers: list[logging.Handler] = [
        logging.FileHandler(log_path, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ]
    logging.basicConfig(level=logging.INFO, format=fmt, handlers=handlers, force=True)
    log = logging.getLogger(name)
    log.info("log file: %s", log_path)
    return log


def env(name: str, default: str | None = None, *, required: bool = False) -> str:
    val = os.getenv(name, default)
    if required and not val:
        raise SystemExit(f"Missing required env var: {name}")
    return val or ""


def ingest_date() -> str:
    return env("INGEST_DATE") or datetime.now(timezone.utc).strftime("%Y-%m-%d")


def mongo_uri() -> str:
    """Build a MongoDB URI from env. We keep it admin-auth here because the
    aggregation cursors need to read the raw collection."""
    host = env("MONGO_HOST", "127.0.0.1")
    port = env("MONGO_PORT", "27017")
    user = env("MONGO_ADMIN_USER", required=True)
    pwd = env("MONGO_ADMIN_PWD", required=True)
    return f"mongodb://{quote_plus(user)}:{quote_plus(pwd)}@{host}:{port}/admin"
