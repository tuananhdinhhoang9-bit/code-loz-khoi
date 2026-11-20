import os

import pytest

from app.main import create_app


@pytest.mark.integration
@pytest.mark.skipif(os.getenv("RUN_DB_TESTS") != "1", reason="Set RUN_DB_TESTS=1 with PostgreSQL running")
def test_real_postgres_health():
    app = create_app()
    try:
        response = app.test_client().get("/health")
        assert response.status_code == 200
        assert response.json["database"] == "ok"
    finally:
        engine = app.extensions["db_engine"]
        if engine is not None:
            engine.dispose()
