import os
import shutil
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CAPTURES = Path(tempfile.mkdtemp(prefix="smarttrap-test-"))
FIRMWARE = Path(tempfile.mkdtemp(prefix="smarttrap-fw-"))

os.environ["DATABASE_URL"] = "postgresql+psycopg://smarttrap:smarttrap@localhost:5433/smarttrap_test"
os.environ["JWT_SECRET"] = "test-jwt-secret-with-32-bytes-min"
os.environ["ADMIN_EMAIL"] = "admin@smarttrap.local"
os.environ["ADMIN_PASSWORD"] = "admin123"
os.environ["ADMIN_NAME"] = "SuperAdmin"
os.environ["USER_EMAIL"] = "usuario@smarttrap.local"
os.environ["USER_PASSWORD"] = "usuario123"
os.environ["USER_NAME"] = "Usuário comum"
os.environ["DEMO_EMAIL"] = "demo@smarttrap.local"
os.environ["DEMO_NAME"] = "Conta demonstração"
os.environ["GATEWAY_API_KEY"] = "test-gateway-key"
os.environ["CAPTURES_DIR"] = str(CAPTURES)
os.environ["FIRMWARE_DIR"] = str(FIRMWARE)
os.environ["CORS_ORIGINS"] = "http://localhost:3000"

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

@pytest.fixture(scope="session", autouse=True)
def migrated_database():
    admin = create_engine(
        "postgresql+psycopg://smarttrap:smarttrap@localhost:5433/postgres",
        isolation_level="AUTOCOMMIT",
    )
    with admin.connect() as connection:
        connection.execute(
            text(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = 'smarttrap_test' AND pid <> pg_backend_pid()"
            )
        )
        connection.execute(text("DROP DATABASE IF EXISTS smarttrap_test"))
        connection.execute(text("CREATE DATABASE smarttrap_test"))
    admin.dispose()
    command.upgrade(Config(str(ROOT / "alembic.ini")), "head")
    yield


@pytest.fixture
def db(migrated_database):
    from app.db.session import SessionLocal
    from app.services.seed import seed

    session = SessionLocal()
    session.execute(text("TRUNCATE TABLE firmware, metrics, captures, devices, gateways, users CASCADE"))
    session.commit()
    for directory in (CAPTURES, FIRMWARE):
        for child in list(directory.iterdir()):
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()
    seed(session)
    session.close()
    yield


@pytest.fixture
def client(db):
    from fastapi.testclient import TestClient
    from app.main import app

    with TestClient(app) as test_client:
        yield test_client
