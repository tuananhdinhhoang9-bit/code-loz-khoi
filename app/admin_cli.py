"""Lệnh vận hành cho VPS: tài khoản nội bộ, dọn dẹp, trạng thái hàng đợi và ổ đĩa."""

import click
from flask import current_app
from sqlalchemy.exc import SQLAlchemyError

from app import auth_local
from app.maintenance import cleanup_all, disk_status
from app.queue_local import QueueError
from app.queue_pg import make_broker
from app.storage import storage


def register_admin_commands(app):
    def engine():
        result = app.extensions["db_engine"]
        if result is None:
            raise click.ClickException("Configure the PostgreSQL connection first")
        return result

    def run(action, *args):
        try:
            return action(engine(), *args)
        except ValueError as error:
            raise click.ClickException(str(error)) from None
        except SQLAlchemyError:
            raise click.ClickException("Database operation failed; check the connection and run init-db") from None

    # Mật khẩu chỉ được nhập qua prompt ẩn, không bao giờ qua tham số dòng lệnh.
    @app.cli.command("create-user")
    @click.argument("email")
    @click.option("--admin", is_flag=True, help="Allow access to the monitoring endpoint")
    @click.password_option(help="Prompted, never passed on the command line")
    def create_user(email, admin, password):
        """Create one local account (AUTH_PROVIDER=local). No default accounts exist."""
        click.echo("Created user " + run(auth_local.create_user, email, password, admin))

    @app.cli.command("set-password")
    @click.argument("email")
    @click.password_option()
    def set_password(email, password):
        """Change a password and sign the user out everywhere."""
        run(auth_local.set_password, email, password)
        click.echo("Password changed; existing sessions revoked.")

    @app.cli.command("disable-user")
    @click.argument("email")
    def disable_user(email):
        """Block sign-in and revoke sessions without deleting the user's videos."""
        run(auth_local.set_active, email, False)
        click.echo("User disabled.")

    @app.cli.command("enable-user")
    @click.argument("email")
    def enable_user(email):
        run(auth_local.set_active, email, True)
        click.echo("User enabled.")

    @app.cli.command("cleanup")
    @click.option("--max-age-hours", default=24, type=click.IntRange(1, 720))
    def cleanup(max_age_hours):
        """Remove old temporary attempts, abandoned uploads and unreferenced outputs."""
        try:
            result = cleanup_all(engine(), storage(), current_app.config["WORK_ROOT"], max_age_hours)
        except (SQLAlchemyError, OSError):
            raise click.ClickException("Cleanup failed; nothing outside the configured folders was touched") from None
        click.echo(f"Cleanup removed: {result}")

    @app.cli.command("system-status")
    def system_status():
        """Show queue counts and free disk space; no secrets or object paths."""
        if current_app.config.get("STORAGE_BACKEND") == "s3":
            click.echo("storage: Amazon S3 bucket (no local disk to measure)")
        else:
            disk = disk_status(storage().root)
            click.echo(f"storage: free={disk['free_bytes']} bytes, used={disk['used_percent']}%")
        try:
            click.echo(f"queue: {make_broker(current_app, engine()).counts()}")
        except (SQLAlchemyError, QueueError):
            raise click.ClickException("Queue status unavailable; check the database or the SQS queue") from None
