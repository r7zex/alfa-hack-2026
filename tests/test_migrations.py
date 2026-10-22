"""Exercise Alembic's real CLI without requiring a PostgreSQL server."""

import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

from app.models import Base


ROOT = Path(__file__).resolve().parents[1]


def run_alembic(*args: str, cwd: Path) -> str:
    env = os.environ.copy()
    env["DB_PASSWORD"] = "migration-test-only"
    env.pop("PYTHONPATH", None)
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", str(ROOT / "alembic.ini"), *args],
        cwd=cwd,
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )
    return result.stdout


def test_upgrade_sql_works_outside_project_directory(tmp_path: Path) -> None:
    sql = run_alembic("upgrade", "head", "--sql", cwd=tmp_path)
    for table in ("businesses", "ip_details", "legal_details", "users"):
        assert f"CREATE TABLE {table} (" in sql
    assert "FOREIGN KEY(business_id) REFERENCES businesses (id)" in sql


def test_downgrade_sql_removes_enum_types_after_tables(tmp_path: Path) -> None:
    sql = run_alembic("downgrade", "head:base", "--sql", cwd=tmp_path)
    for enum_type in ("userrole", "businesstype"):
        assert f"DROP TYPE {enum_type};" in sql
        assert sql.index("DROP TABLE businesses;") < sql.index(f"DROP TYPE {enum_type};")


def test_migration_round_trip_matches_models(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # SQLite covers the online migration path; native PostgreSQL ENUM DDL is
    # covered separately by the offline SQL tests above.
    url = "sqlite:///" + (tmp_path / "migration.sqlite").as_posix()
    monkeypatch.setattr(
        "app.settings.get_settings", lambda: SimpleNamespace(database_url=url)
    )
    config = Config(str(ROOT / "alembic.ini"))
    engine = create_engine(url)
    try:
        command.upgrade(config, "head")
        command.check(config)
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO users (email, password_hash, role) "
                    "VALUES (:email, :password, :role)"
                ),
                {"email": "admin@example.com", "password": "test", "role": "ADMIN"},
            )
        command.upgrade(config, "head")
        with engine.connect() as connection:
            assert connection.scalar(text("SELECT count(*) FROM users")) == 1
        command.downgrade(config, "base")
        assert set(inspect(engine).get_table_names()) == {"alembic_version"}
        command.upgrade(config, "head")
        command.check(config)
        assert set(inspect(engine).get_table_names()) == {
            "alembic_version", *Base.metadata.tables
        }
    finally:
        engine.dispose()
