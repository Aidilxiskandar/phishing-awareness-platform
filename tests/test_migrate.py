"""app.migrate brings fresh, legacy (create_all) and managed databases to head."""
import pytest
from sqlalchemy import inspect, text
from sqlmodel import SQLModel

from app.database import engine
from app.migrate import migrate


@pytest.fixture(autouse=True)
def _drop_alembic_version():
    yield
    # Not part of SQLModel.metadata, so the shared fixture wouldn't drop it, and
    # init_db would then skip create_all for every later test.
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS alembic_version"))


def _columns(table):
    return {c["name"] for c in inspect(engine).get_columns(table)}


def _head_recorded():
    with engine.connect() as conn:
        return conn.execute(text("SELECT version_num FROM alembic_version")).scalar()


def test_fresh_database_gets_full_schema():
    SQLModel.metadata.drop_all(engine)
    assert migrate() == "fresh"
    tables = set(inspect(engine).get_table_names())
    assert set(SQLModel.metadata.tables) <= tables
    assert "erased_at" in _columns("user")
    assert _head_recorded()


def test_legacy_database_is_stamped_then_upgraded():
    # The shared fixture builds the schema with create_all -> a "legacy" DB.
    assert "alembic_version" not in inspect(engine).get_table_names()
    assert migrate() == "legacy"
    assert _head_recorded()
    assert migrate() == "managed"  # idempotent on the next start


def test_legacy_database_missing_new_column_gets_it():
    with engine.begin() as conn:
        conn.execute(text('ALTER TABLE "user" DROP COLUMN erased_at'))
    assert "erased_at" not in _columns("user")
    assert migrate() == "legacy"
    assert "erased_at" in _columns("user")
