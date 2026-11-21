import json
import time
from types import SimpleNamespace
from uuid import uuid4

import firebase_admin
from firebase_admin import _token_gen, credentials
from google.auth.credentials import AnonymousCredentials
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
import jwt
import pytest

from app.main import create_app


class TestCredential(credentials.Base):
    def get_credential(self):
        return AnonymousCredentials()


@pytest.mark.parametrize("change,status", [({}, 200), ({"exp": 1}, 401), ({"aud": "wrong-project"}, 401), ({"iss": "https://wrong-issuer"}, 401), ({"bad_signature": True}, 401)])
def test_sdk_verifies_real_rsa_tokens(monkeypatch, change, status):
    monkeypatch.delenv("FIREBASE_AUTH_EMULATOR_HOST", raising=False)
    project = "sdk-" + uuid4().hex
    name = "video-portal-" + project
    firebase_app = firebase_admin.initialize_app(TestCredential(), {"projectId": project}, name=name)
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public = key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    monkeypatch.setattr(_token_gen.CertificateFetchRequest, "__call__", lambda *args, **kwargs: SimpleNamespace(status=200, data=json.dumps({"test-key": public}).encode(), headers={}))
    now = int(time.time())
    claims = {"sub": "signed-owner", "aud": project, "iss": "https://securetoken.google.com/" + project, "iat": now - 10, "exp": now + 300, "auth_time": now - 10}
    bad_signature = change.get("bad_signature", False)
    claims.update({k: v for k, v in change.items() if k != "bad_signature"})
    signing_key = rsa.generate_private_key(public_exponent=65537, key_size=2048) if bad_signature else key
    token = jwt.encode(claims, signing_key, algorithm="RS256", headers={"kid": "test-key"})
    try:
        app = create_app({"TESTING": True, "FIREBASE_PROJECT_ID": project})
        response = app.test_client().get("/api/me", headers={"Authorization": "Bearer " + token})
        assert response.status_code == status
        if status == 200:
            assert response.json["uid"] == "signed-owner"
    finally:
        firebase_admin.delete_app(firebase_app)
