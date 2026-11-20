"""Bring any database up to the latest schema, then exit.

    python -m app.migrate

Safe to run on every start (the Docker image does). Handles three cases:

  * empty database           -> ``alembic upgrade head`` creates the full schema
  * already Alembic-managed  -> ``alembic upgrade head`` applies new migrations
  * legacy database built by ``create_all`` (no ``alembic_version`` table, e.g.
    an older dev DB or Docker volume) -> stamped at the baseline revision first,
    then upgraded. Migrations after the baseline are written to tolerate changes
    ``create_all`` may already have made.
"""
from __future__ import annotations

import logging
from pathlib import Path

from alembic.config import Config
from sqlalchemy import inspect

from alembic import command
from app.database import engine

logger = logging.getLogger("phishguard.migrate")

ROOT = Path(__file__).resolve().parent.parent
BASELINE_REVISION = "89a0e753d8df"  # initial schema


def _alembic_config() -> Config:
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "alembic"))
    return cfg


def migrate() -> str:
    """Upgrade to head. Returns which path was taken: fresh / legacy / managed."""
    tables = set(inspect(engine).get_table_names())
    cfg = _alembic_config()
    if "alembic_version" in tables:
        state = "managed"
    elif tables:
        state = "legacy"
        logger.info("legacy create_all database found; stamping baseline %s",
                    BASELINE_REVISION)
        command.stamp(cfg, BASELINE_REVISION)
    else:
        state = "fresh"
    command.upgrade(cfg, "head")
    logger.info("database schema at head (%s)", state)
    return state


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(f"Database migrated ({migrate()}).")
