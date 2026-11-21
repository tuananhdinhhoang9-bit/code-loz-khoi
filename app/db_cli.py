from pathlib import Path

import click
from sqlalchemy.exc import SQLAlchemyError

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.models import Base, OutputProfile
from app.seed import seed_database, seed_id

# Cột được thêm sau Phase 02. Chỉ thêm (ADD COLUMN IF NOT EXISTS), không bao giờ xoá hay đổi kiểu.
ADDED_COLUMNS = [("transcode_jobs", "progress_percent", "INTEGER")]


def upgrade_schema(engine):
    """Cơ chế migration của dự án: tạo bảng còn thiếu rồi thêm cột còn thiếu; chạy lại nhiều lần vẫn an toàn."""
    Base.metadata.create_all(engine)
    schema = (engine.get_execution_options().get("schema_translate_map") or {}).get(None)
    prefix = f'"{schema}".' if schema else ""
    with engine.begin() as connection:
        for table, column, kind in ADDED_COLUMNS:
            connection.execute(text(f'ALTER TABLE {prefix}"{table}" ADD COLUMN IF NOT EXISTS "{column}" {kind}'))
    # Hệ thống chỉ có một profile đầu ra; thiếu nó thì không tạo được job. Dùng cùng ID với seed
    # để chạy seed-db sau đó không bị xung đột.
    with Session(engine) as session, session.begin():
        if session.scalar(select(OutputProfile).where(OutputProfile.name == "mp4-480p")) is None:
            session.add(OutputProfile(id=seed_id("mp4-480p"), name="mp4-480p"))


def register_commands(app):
    def database_engine():
        engine = app.extensions["db_engine"]
        if engine is None:
            raise click.ClickException("Configure the local PostgreSQL connection first")
        return engine

    @app.cli.command("init-db")
    def init_db():
        """Create missing tables and additive columns without dropping existing data."""
        try:
            upgrade_schema(database_engine())
        except SQLAlchemyError:
            raise click.ClickException("Database initialization failed; check the local DB connection") from None
        click.echo("Database tables ready; existing tables/data preserved.")

    @app.cli.command("seed-db")
    @click.option("--media-dir", default=".local/seed", type=click.Path(path_type=Path))
    def seed_db(media_dir):
        """Insert deterministic local fixtures without replacing existing rows."""
        try:
            seed_database(database_engine(), media_dir)
        except (ValueError, OSError, KeyError, SQLAlchemyError):
            raise click.ClickException("Seed failed; check the dataset manifest, schema and seed conflicts; no DB changes committed") from None
        click.echo("Seed ready: ten queued videos/jobs, one profile, five permissions and ten outbox events; no outputs published.")
