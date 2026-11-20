from unittest.mock import MagicMock

from sqlalchemy.exc import OperationalError

from app.main import create_app


def test_home_renders_without_database():
    app = create_app({"TESTING": True})
    response = app.test_client().get("/")
    assert response.status_code == 200
    assert b"Video Upload and Processing Portal" in response.data
    assert b'href="/health"' in response.data
    assert response.headers["Cache-Control"] == "no-store"


def test_unconfigured_database_is_not_healthy():
    app = create_app({"TESTING": True})
    response = app.test_client().get("/health")
    assert response.status_code == 503
    assert response.json["database"] == "unavailable"
    assert response.json["request_id"] == response.headers["X-Request-ID"]


def test_health_executes_query():
    app = create_app({"TESTING": True})
    engine = MagicMock()
    connection = engine.connect.return_value.__enter__.return_value
    connection.execute.return_value.scalar_one.return_value = 1
    app.extensions["db_engine"] = engine
    response = app.test_client().get("/health")
    assert response.status_code == 200
    assert response.json["database"] == "ok"
    assert str(connection.execute.call_args.args[0]) == "SELECT 1"
    engine.connect.return_value.__exit__.assert_called_once()


def test_failed_database_does_not_leak_exception(caplog):
    app = create_app({"TESTING": True})
    engine = MagicMock()
    engine.connect.side_effect = OperationalError("private-connection-marker", {}, Exception())
    app.extensions["db_engine"] = engine
    response = app.test_client().get("/health")
    assert response.status_code == 503
    assert "private-connection-marker" not in response.get_data(as_text=True)
    assert "private-connection-marker" not in caplog.text


def test_actual_unreachable_postgres_returns_503():
    app = create_app({
        "TESTING": True,
        "DATABASE_URL": "postgresql+psycopg://test:test@127.0.0.1:1/test",
    })
    try:
        response = app.test_client().get("/health")
        assert response.status_code == 503
        assert response.json["database"] == "unavailable"
    finally:
        app.extensions["db_engine"].dispose()
