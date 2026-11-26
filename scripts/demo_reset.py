"""Reset the public demo to a fresh, realistic state (DEMO_MODE only).

Wipes all data (schema and migrations are kept), re-seeds the training course,
then replays three drills through the running server with the drill simulator,
so the dashboard, trend, reports and evidence log always look lived-in.

Runs inside the web container, e.g. nightly from the host's cron:
    docker compose -f docker-compose.prod.yml -f docker-compose.demo.yml \\
        exec -T web python scripts/demo_reset.py

Refuses to run unless DEMO_MODE is on, so it can never wipe a real deployment.
"""
from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))  # run as `python scripts/demo_reset.py` from /app

from sqlmodel import SQLModel  # noqa: E402

import app.models  # noqa: E402,F401  (registers every table on SQLModel.metadata)
from app.config import settings  # noqa: E402
from app.database import engine, init_db  # noqa: E402

BASE = os.environ.get("DEMO_BASE", "http://127.0.0.1:8000")

# (campaign name, subject, days before now, simulator seed, extra staff to add)
DRILLS = [
    ("IT password expiry drill", "Your password expires today", 84, 3, 300),
    ("Parcel delivery drill", "We could not deliver your parcel", 42, 11, 1),
    ("Payroll update drill", None, 0, 23, 1),
]


def _db_path() -> str:
    url = str(engine.url)
    if not url.startswith("sqlite:///"):
        sys.exit("demo_reset supports the SQLite demo database only")
    return url.removeprefix("sqlite:///")


def wipe() -> None:
    """Delete every row in every app table, children first; keep alembic_version."""
    tables = list(reversed(SQLModel.metadata.sorted_tables))
    if not tables:
        sys.exit("no tables registered; refusing to continue")
    with engine.begin() as conn:
        for table in tables:
            conn.execute(table.delete())
    init_db()  # re-seed the training course


def run_drill(seed: int, staff: int) -> None:
    cmd = [sys.executable, str(HERE / "simulate_drill.py"), "--base", BASE, "--db", _db_path(),
           "--seed", str(seed), "--staff", str(staff),
           "--user", settings.admin_username, "--password", settings.effective_admin_password,
           "--window", str(settings.scanner_time_window_seconds)]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL)


def stage(db: str) -> None:
    """Name the campaigns and spread them over the quarter so the trend reads well."""
    con = sqlite3.connect(db)
    ids = [r[0] for r in con.execute("SELECT id FROM campaign ORDER BY id")]
    if len(ids) != len(DRILLS):
        sys.exit(f"expected {len(DRILLS)} campaigns after the replay, found {len(ids)}")
    for cid, (name, subject, days, _, _) in zip(ids, DRILLS, strict=True):
        con.execute("UPDATE campaign SET name=? WHERE id=?", (name, cid))
        if subject:
            con.execute("UPDATE campaign SET subject=? WHERE id=?", (subject, cid))
        if days:
            shift = f"-{days} days"
            con.execute("UPDATE campaign SET sent_at=datetime(sent_at,?), "
                        "created_at=datetime(created_at,?) WHERE id=?", (shift, shift, cid))
            for col in ("sent_at", "reported_at"):
                con.execute(f"UPDATE target SET {col}=datetime({col},?) "
                            f"WHERE campaign_id=? AND {col} IS NOT NULL", (shift, cid))
            con.execute("UPDATE event SET created_at=datetime(created_at,?) WHERE campaign_id=?",
                        (shift, cid))
    con.commit()
    con.close()


def main() -> None:
    if not settings.demo_mode and os.environ.get("DEMO_RESET_FORCE") != "1":
        sys.exit("Refusing: DEMO_MODE is off. This script wipes all data.")
    print("demo reset: wiping data")
    wipe()
    for name, _, _, seed, staff in DRILLS:
        print(f"demo reset: replaying '{name}'")
        run_drill(seed, staff)
    stage(_db_path())
    print("demo reset: done")


if __name__ == "__main__":
    main()
