"""Create the raw schemas (sql/0*.sql) in the target database. Safe to re-run."""
import sys
from pathlib import Path

import psycopg

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from envconfig import database_url, load_env  # noqa: E402


def main() -> None:
    load_env()
    files = sorted((ROOT / "sql").glob("0*.sql"))
    with psycopg.connect(database_url(), autocommit=True) as conn:
        for f in files:
            conn.execute(f.read_text(encoding="utf-8"))
            print(f"applied {f.name}")


if __name__ == "__main__":
    main()
