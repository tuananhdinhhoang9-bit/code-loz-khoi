from uuid import uuid4

from firebase_admin import auth
import pytest
from sqlalchemy.orm import Session

from app.main import create_app
from app.models import Video, VideoPermission


def test_verifier(token):
    if token == "expired":
        raise auth.ExpiredIdTokenError("expired", cause=None)
    if token not in ["owner", "viewer", "stranger", "admin"]:
        raise ValueError("invalid token")
    return {"uid": token, "admin": token == "admin"}


test_verifier.__test__ = False


@pytest.fixture
def auth_client(schema_engine):
    with Session(schema_engine) as session, session.begin():
        video = Video(owner_uid="owner", title="Private title", input_object="secret/object.mp4", source_generation="test-v1", size_bytes=12, mime_type="video/mp4")
        session.add(video)
        session.flush()
        session.add(VideoPermission(video_id=video.id, viewer_uid="viewer"))
        video_id = video.id
    app = create_app({"TESTING": True, "TOKEN_VERIFIER": test_verifier})
    app.extensions["db_engine"] = schema_engine
    return app.test_client(), video_id


@pytest.mark.parametrize("token,status", [(None, 401), ("expired", 401), ("bad", 401), ("owner", 200), ("viewer", 200), ("stranger", 404)])
def test_direct_private_api(auth_client, token, status):
    client, video_id = auth_client
    headers = {"Authorization": "Bearer " + token} if token else {}
    response = client.get(f"/api/videos/{video_id}", headers=headers)
    assert response.status_code == status
    assert response.json["request_id"] == response.headers["X-Request-ID"]
    assert "secret/object" not in response.get_data(as_text=True)
    if status != 200:
        assert "Private title" not in response.get_data(as_text=True)


def test_uid_body_and_headers_cannot_impersonate_owner(auth_client):
    client, video_id = auth_client
    response = client.get(f"/api/videos/{video_id}", json={"uid": "owner"}, headers={"Authorization": "Bearer stranger", "X-User-ID": "owner"})
    assert response.status_code == 404


def test_revoked_permission_is_denied(auth_client, schema_engine):
    client, video_id = auth_client
    with Session(schema_engine) as session, session.begin():
        session.delete(session.get(VideoPermission, (video_id, "viewer")))
    assert client.get(f"/api/videos/{video_id}", headers={"Authorization": "Bearer viewer"}).status_code == 404


def test_test_hook_and_emulator_blocked_in_runtime(monkeypatch):
    with pytest.raises(ValueError, match="only in tests"):
        create_app({"TOKEN_VERIFIER": test_verifier})
    monkeypatch.setenv("FIREBASE_AUTH_EMULATOR_HOST", "127.0.0.1:9099")
    with pytest.raises(ValueError, match="not allowed"):
        create_app({})


def test_unconfigured_runtime_fails_closed(monkeypatch):
    monkeypatch.delenv("FIREBASE_AUTH_EMULATOR_HOST", raising=False)
    app = create_app({})
    response = app.test_client().get("/api/me", headers={"Authorization": "Bearer not-a-real-token"})
    assert response.status_code == 503
    assert response.json["error"] == "auth_not_configured"
    assert app.test_client().get("/api/auth/config").status_code == 503


def test_auth_config_only_exposes_public_web_key():
    app = create_app({"TESTING": True, "FIREBASE_PROJECT_ID": "test-project", "FIREBASE_WEB_API_KEY": "test-public-web-key"})
    response = app.test_client().get("/api/auth/config")
    assert response.status_code == 200
    assert set(response.json) == {"api_key", "request_id"}


def test_official_sdk_called_with_configured_project(monkeypatch):
    import firebase_admin
    from app import auth as portal_auth
    calls = []
    monkeypatch.setattr(portal_auth.auth, "verify_id_token", lambda token, app: calls.append((token, app.project_id)) or {"uid": "verified-user"})
    app = create_app({"TESTING": True, "FIREBASE_PROJECT_ID": "local-sdk-test"})
    try:
        response = app.test_client().get("/api/me", headers={"Authorization": "Bearer sdk-token"})
        assert response.status_code == 200
        assert calls == [("sdk-token", "local-sdk-test")]
    finally:
        firebase_admin.delete_app(firebase_admin.get_app("video-portal-local-sdk-test"))
