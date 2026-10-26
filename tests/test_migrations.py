"""Exercise Alembic's real CLI without requiring a PostgreSQL server."""

import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import (
    CHAR,
    CheckConstraint,
    Column,
    DateTime,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    create_engine,
    func,
    inspect,
    text,
)

from app.models.auth import Base


ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.skipif(not os.getenv('TEST_MIGRATION_DATABASE_URL'),reason='Separate PostgreSQL migration database required')
def test_postgres_incremental_upgrade_preserves_account_session_and_draft(monkeypatch):
    from uuid import uuid4
    url=os.environ['TEST_MIGRATION_DATABASE_URL']
    assert 'migration' in url.rsplit('/',1)[-1], 'Use an empty disposable migrations database'
    monkeypatch.setattr('app.settings.get_settings',lambda:SimpleNamespace(database_url=url))
    config=Config(str(ROOT/'alembic.ini'));engine=create_engine(url)
    assert not inspect(engine).has_table('alembic_version'),'Migration test requires an empty database'
    command.upgrade(config,'a2026c001001')
    id_=uuid4()
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO users (id,email,password_hash,role,is_demo) VALUES (9001,'preserved@example.com','old-hash','ADMIN',false)"))
        conn.execute(text("INSERT INTO auth_sessions (id,user_id,token_hash,csrf_hash,expires_at,created_at) VALUES (:id,9001,:token,:csrf,now()+interval '1 day',now())"),{'id':str(id_),'token':'a'*64,'csrf':'b'*64})
        conn.execute(text("INSERT INTO loan_applications (id,owner_id,product_id,amount,months,status,current_step) VALUES (:id,'legacy','working',1000000,12,'draft',2)"),{'id':id_})
    command.upgrade(config,'head');command.check(config)
    with engine.connect() as conn:
        assert conn.execute(text('SELECT email,password_hash,can_sign FROM users WHERE id=9001')).one()==('preserved@example.com','old-hash',True)
        assert conn.scalar(text('SELECT count(*) FROM auth_sessions WHERE user_id=9001'))==1
        assert conn.execute(text('SELECT amount,status,current_step,decision_mode FROM loan_applications')).one()==(1000000,'draft',2,'manual')
    engine.dispose()


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
        assert sql.index("DROP TABLE businesses;") < sql.index(
            f"DROP TYPE {enum_type};"
        )


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
            "alembic_version",
            *Base.metadata.tables,
        }
    finally:
        engine.dispose()


def test_incremental_auth_upgrade_preserves_existing_accounts(tmp_path, monkeypatch):
    url = "sqlite:///" + (tmp_path / "existing.sqlite").as_posix()
    monkeypatch.setattr(
        "app.settings.get_settings", lambda: SimpleNamespace(database_url=url)
    )
    config = Config(str(ROOT / "alembic.ini"))
    engine = create_engine(url)
    try:
        command.upgrade(config, "1bd2be57b412")
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO users (email, password_hash, role) VALUES ('existing@example.com', 'old-hash', 'ADMIN')"
                )
            )
        command.upgrade(config, "head")
        command.check(config)
        with engine.connect() as connection:
            assert connection.execute(
                text("SELECT email, password_hash, is_demo FROM users")
            ).one() == ("existing@example.com", "old-hash", 0)
        command.downgrade(config, "1bd2be57b412")
        with engine.connect() as connection:
            assert connection.scalar(text("SELECT count(*) FROM users")) == 1
    finally:
        engine.dispose()


@pytest.mark.parametrize("legacy_step", [True, False])
def test_existing_loan_drafts_survive_auth_merge(tmp_path, monkeypatch, legacy_step):
    from uuid import uuid4

    url = "sqlite:///" + (tmp_path / "legacy-loans.sqlite").as_posix()
    monkeypatch.setattr(
        "app.settings.get_settings", lambda: SimpleNamespace(database_url=url)
    )
    config = Config(str(ROOT / "alembic.ini"))
    engine = create_engine(url)
    try:
        # Compile the legacy schema with SQLAlchemy: inline SQL with all
        # CHECK clauses on one line can confuse SQLite constraint reflection
        # during Alembic's batch table recreation.
        legacy_table = Table(
            "loan_applications",
            MetaData(),
            Column("id", CHAR(32), primary_key=True),
            Column("owner_id", String(100), nullable=False),
            Column("product_id", String(40), nullable=False),
            Column("amount", Integer, nullable=False),
            Column("months", Integer, nullable=False),
            Column("purpose", Text),
            Column("revenue", Integer),
            Column("expenses", Integer),
            Column("debt_payment", Integer),
            Column("status", String(20), nullable=False),
            Column(
                "created_at", DateTime(timezone=True),
                server_default=func.now(), nullable=False,
            ),
            Column(
                "updated_at", DateTime(timezone=True),
                server_default=func.now(), nullable=False,
            ),
            Column("current_step", Integer, server_default="0", nullable=False),
            CheckConstraint("amount > 0", name="loan_amount_positive"),
            CheckConstraint("months > 0", name="loan_months_positive"),
            CheckConstraint(
                "revenue IS NULL OR revenue >= 0",
                name="loan_revenue_nonnegative",
            ),
            CheckConstraint(
                "expenses IS NULL OR expenses >= 0",
                name="loan_expenses_nonnegative",
            ),
            CheckConstraint(
                "debt_payment IS NULL OR debt_payment >= 0",
                name="loan_debt_nonnegative",
            ),
            Index("ix_loan_applications_owner_id", "owner_id"),
        )
        legacy_table.create(engine)
        assert {
            check["name"]
            for check in inspect(engine).get_check_constraints("loan_applications")
        } == {
            "loan_amount_positive",
            "loan_months_positive",
            "loan_revenue_nonnegative",
            "loan_expenses_nonnegative",
            "loan_debt_nonnegative",
        }
        row_id = uuid4()
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO loan_applications (id, owner_id, product_id, amount, months, status, current_step) "
                    "VALUES (:id, 'demo-ip', 'working', 1000000, 12, 'draft', 2)"
                ),
                {"id": row_id.hex}
            )
            if not legacy_step:
                connection.execute(
                    text("ALTER TABLE loan_applications DROP COLUMN current_step")
                )
        command.upgrade(config, "head")
        command.check(config)
        with engine.connect() as connection:
            assert connection.execute(
                text(
                    "SELECT owner_id, amount, status, current_step FROM loan_applications"
                )
            ).one() == ("demo-ip", 1000000, "draft", 2 if legacy_step else 0)
            assert connection.scalar(text("SELECT business_id FROM loan_applications")) is None
        command.upgrade(config, "head")
        with engine.connect() as connection:
            assert (
                connection.scalar(text("SELECT count(*) FROM loan_applications")) == 1
            )
    finally:
        engine.dispose()
