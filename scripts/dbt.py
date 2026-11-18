"""
Run dbt against the same database the Python scripts use (DATABASE_URL in .env / .env.local),
on any OS and without Docker. Converts the URL into the PG* variables dbt's profile reads.

    python scripts/dbt.py docs generate
    python scripts/dbt.py docs serve            # lineage graph on http://localhost:8080
    python scripts/dbt.py test
    python scripts/dbt.py build --allow-write   # see below

Commands that write tables (build, run, seed, snapshot) go straight into the schemas the dashboard
reads, skipping write-audit-publish. On a hosted database they are refused unless you pass
--allow-write; use scripts/dbt_wap.sh for real builds.
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
from envconfig import database_url, load_env  # noqa: E402
from pg_env_from_url import pg_env  # noqa: E402

WRITE_COMMANDS = {"build", "run", "seed", "snapshot"}
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "db"}


def find_dbt() -> str:
    found = shutil.which("dbt")
    if found:
        return found
    for candidate in (Path(sys.executable).parent / "Scripts" / "dbt.exe",   # Windows venv / install
                      Path(sys.executable).parent / "dbt"):
        if candidate.exists():
            return str(candidate)
    raise SystemExit("dbt not found: run `pip install -r requirements.txt` first")


def main(argv: list[str]) -> int:
    allow_write = "--allow-write" in argv
    args = [a for a in argv if a != "--allow-write"]
    if not args:
        print(__doc__)
        return 2

    load_env()
    env = {**os.environ, **pg_env(database_url())}

    if args[0] in WRITE_COMMANDS and env["PGHOST"] not in LOCAL_HOSTS and not allow_write:
        print(f"refusing `dbt {args[0]}` on {env['PGHOST']}: it would overwrite the published tables "
              "without write-audit-publish.\nUse `bash scripts/dbt_wap.sh` (Git Bash), or pass "
              "--allow-write if you really mean it.", file=sys.stderr)
        return 1

    dbt_dir = ROOT / "dbt"
    if not (dbt_dir / "profiles.yml").exists():
        shutil.copy(dbt_dir / "profiles.yml.example", dbt_dir / "profiles.yml")
    print(f"dbt -> {env['PGHOST']}/{env['PGDATABASE']} (sslmode={env['PGSSLMODE']})", flush=True)
    return subprocess.call([find_dbt(), *args, "--profiles-dir", "."], cwd=dbt_dir, env=env)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
