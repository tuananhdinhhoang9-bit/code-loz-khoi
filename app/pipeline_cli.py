import logging
from pathlib import Path

import click
from flask import current_app
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.models import OutboxEvent, TranscodeJob
from app.pipeline import dispatch_one, reconcile, relay, retry_failed_job
from app.queue_local import FileBroker, QueueError, require_local_runtime
from app.storage import storage


def register_pipeline_commands(app):
    def engine():
        result = app.extensions["db_engine"]
        if result is None:
            raise click.ClickException("Configure the local database first")
        return result

    @app.cli.command("local-process")
    @click.option("--limit", default=1, type=click.IntRange(1, 10))
    def local_process(limit):
        """Run one bounded local relay/dispatch cycle; repeat after retry delays."""
        try:
            # File queue + Docker chỉ dành cho máy phát triển; VPS dùng `python -m app.worker_service`.
            require_local_runtime()
            db = engine()
            root = Path(current_app.config["STORAGE_ROOT"]).parent
            broker = FileBroker(root / "queue")
            logging.basicConfig(level=logging.INFO, format="%(message)s")
            logging.getLogger("app.pipeline").setLevel(logging.INFO)
            recovered = reconcile(db)
            published = relay(db, broker, limit=limit)
            outcomes = []
            for _ in range(limit):
                outcome = dispatch_one(db, broker, storage(), root / "work", seed_root=root / "seed")
                outcomes.append(outcome)
                if outcome == "empty":
                    break
            click.echo(f"Local cycle: recovered={recovered}, published={published}, outcomes={outcomes}")
        except (RuntimeError, OSError, QueueError, SQLAlchemyError):
            raise click.ClickException("Local cycle failed; inspect job/attempt IDs with local-jobs; no private details logged") from None

    @app.cli.command("local-jobs")
    def local_jobs():
        """Show bounded operator-visible states without object URLs or secrets."""
        with Session(engine()) as session:
            for job in session.scalars(select(TranscodeJob).order_by(TranscodeJob.queued_at).limit(100)):
                click.echo(f"{job.id} status={job.status} attempts={job.attempts}/{min(job.max_attempts, 3)} error={job.last_error_code or '-'} due={job.lease_until or '-'}")
            failures = session.scalars(select(OutboxEvent).where(OutboxEvent.last_error.is_not(None)).limit(100))
            for event in failures:
                click.echo(f"outbox={event.id} publish_attempts={event.publish_attempts} error={event.last_error}")

    @app.cli.command("retry-job")
    @click.argument("job_id", type=click.UUID)
    def retry_job(job_id):
        """Explicit operator retry of one FAILED local job; never reset READY."""
        try:
            retry_failed_job(engine(), job_id)
        except (ValueError, SQLAlchemyError):
            raise click.ClickException("Retry refused; select a FAILED local job and verify DB access") from None
        click.echo("FAILED job requeued for a new bounded retry campaign; run local-process.")
