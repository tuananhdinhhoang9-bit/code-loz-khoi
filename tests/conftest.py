import os
import shutil
from uuid import uuid4

import pytest
from sqlalchemy import text

from app.main import create_app
from app.models import Base
from app.seed_media import generate_media


@pytest.fixture
def schema_engine():
    if os.getenv("RUN_DB_TESTS") != "1":
        pytest.skip("Set RUN_DB_TESTS=1 with PostgreSQL running")
    engine = create_app().extensions["db_engine"]
    assert engine is not None, "Configure local PostgreSQL first"
    schema = "test_phase02_" + uuid4().hex
    with engine.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    test_engine = engine.execution_options(schema_translate_map={None: schema})
    try:
        Base.metadata.create_all(test_engine)
        yield test_engine
    finally:
        # Chỉ dọn schema có UUID do chính fixture này vừa tạo, không đụng schema public.
        with engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        engine.dispose()


@pytest.fixture(scope="session")
def seed_media(tmp_path_factory):
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        pytest.skip("FFmpeg and ffprobe are required for real seed media checks")
    directory = tmp_path_factory.mktemp("seed_media")
    generate_media(directory)
    return directory
