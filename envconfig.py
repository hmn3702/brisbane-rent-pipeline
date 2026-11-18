"""
Shared environment loading for the pipeline scripts.

- Reads `.env` and then `.env.local` from the project root. `neon env pull` / `neon deploy`
  write to `.env.local` when no `.env` exists, and `.env.local` wins, as in Node tooling.
  Variables already set in the process (e.g. GitHub Actions secrets) are never overridden.
- database_url() prefers Neon's DATABASE_URL_UNPOOLED (a direct connection) when it is set.
  The loaders use COPY and long transactions, and dbt runs DDL; those are safest on a direct
  connection rather than through the PgBouncer pooler.
"""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def load_env() -> None:
    try:
        from dotenv import dotenv_values
    except ImportError:            # python-dotenv is in requirements.txt; tolerate its absence
        return
    merged: dict[str, str] = {}
    for name in (".env", ".env.local"):
        path = ROOT / name
        if path.exists():
            merged.update({k: v for k, v in dotenv_values(path).items() if v is not None})
    for key, value in merged.items():
        os.environ.setdefault(key, value)


def database_url() -> str:
    url = os.environ.get("DATABASE_URL_UNPOOLED") or os.environ.get("DATABASE_URL")
    if not url:
        raise SystemExit("DATABASE_URL is not set (export it, or put it in .env / .env.local).")
    return url
