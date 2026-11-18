"""
Turn DATABASE_URL into the PG* variables dbt's profile reads, for GitHub Actions.

Prints `::add-mask::` for the password first, so it never appears in logs, then appends
PGHOST / PGPORT / PGUSER / PGPASSWORD / PGDATABASE / PGSSLMODE to $GITHUB_ENV.

    python scripts/pg_env_from_url.py   # reads DATABASE_URL, writes to $GITHUB_ENV
"""
import os
import sys
from urllib.parse import parse_qs, unquote, urlparse


def pg_env(url: str) -> dict[str, str]:
    u = urlparse(url)
    if u.scheme not in ("postgres", "postgresql"):
        raise ValueError("DATABASE_URL must start with postgresql://")
    query = parse_qs(u.query)
    host = u.hostname or "localhost"
    default_ssl = "prefer" if host in ("localhost", "127.0.0.1") else "require"
    return {
        "PGHOST": host,
        "PGPORT": str(u.port or 5432),
        "PGUSER": unquote(u.username or ""),
        "PGPASSWORD": unquote(u.password or ""),
        "PGDATABASE": (u.path or "/").lstrip("/") or "postgres",
        "PGSSLMODE": query.get("sslmode", [default_ssl])[0],
    }


def main() -> int:
    env = pg_env(os.environ["DATABASE_URL"])
    if env["PGPASSWORD"]:
        print(f"::add-mask::{env['PGPASSWORD']}")
    target = os.environ.get("GITHUB_ENV")
    lines = "".join(f"{k}={v}\n" for k, v in env.items())
    if target:
        with open(target, "a") as f:
            f.write(lines)
    else:
        sys.stdout.write("".join(f"{k}={'***' if k == 'PGPASSWORD' else v}\n" for k, v in env.items()))
    print(f"dbt will connect to {env['PGHOST']}:{env['PGPORT']}/{env['PGDATABASE']} (sslmode={env['PGSSLMODE']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
