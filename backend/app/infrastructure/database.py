import os
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from alembic import command
from alembic.config import Config

def database_url() -> str:
    url = os.environ.get("DATABASE_URL", "")
    if not url.startswith("postgresql+psycopg://"):
        raise RuntimeError("Set DATABASE_URL to a PostgreSQL psycopg connection URL")
    return url

def make_engine(url: str):
    return create_engine(url, pool_pre_ping=True, pool_size=4, max_overflow=0)

def migrate(engine) -> None:
    cfg = Config()
    cfg.set_main_option("script_location", str(Path(__file__).resolve().parents[2] / "migrations"))
    with engine.connect() as connection:
        connection.exec_driver_sql("SELECT pg_advisory_lock(914202601)")
        connection.commit()
        try:
            cfg.attributes["connection"] = connection
            command.upgrade(cfg, "head")
        finally:
            connection.exec_driver_sql("SELECT pg_advisory_unlock(914202601)")
            connection.commit()

def sessions(engine):
    return sessionmaker(engine, expire_on_commit=False)
