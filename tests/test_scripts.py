"""Kiểm thử phần dùng chung của scripts/smoke_test.py và scripts/seed_remote.py mà không cần máy chủ nào."""

import io
from pathlib import Path
import sys

import pytest
from werkzeug.formparser import parse_form_data

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import portal_client  # noqa: E402
import seed_remote  # noqa: E402


class FakeClient:
    """Ghi lại các lời gọi và trả lời theo kịch bản; không mở kết nối mạng."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []

    def call(self, method, path, body=None, headers=None, auth=True, raw=False):
        self.calls.append({"method": method, "path": path, "body": body, "headers": headers or {}, "auth": auth})
        return self.replies.pop(0)


def test_s3_form_has_signed_fields_first_and_file_last():
    fields = {"key": "inputs/video/source", "Content-Type": "video/mp4", "policy": "signed-policy", "x-amz-signature": "abc"}
    body, content_type = portal_client.encode_form(fields, b"\x00video-bytes\r\n--not-a-boundary")
    environ = {"REQUEST_METHOD": "POST", "CONTENT_TYPE": content_type, "CONTENT_LENGTH": str(len(body)), "wsgi.input": io.BytesIO(body)}
    _, form, files = parse_form_data(environ)
    assert dict(form) == fields
    assert files["file"].read() == b"\x00video-bytes\r\n--not-a-boundary"
    # S3 bỏ qua mọi trường đứng sau file, nên file phải là phần cuối cùng của thân.
    assert body.rindex(b'name="file"') > max(body.index(f'name="{name}"'.encode()) for name in fields)


def test_upload_follows_the_method_the_server_returned():
    put = FakeClient([(201, b"", {})])
    assert portal_client.upload(put, {"upload_url": "/local-storage/upload?ticket=t", "upload_method": "PUT"}, b"abc", "video/mp4") == (True, 201)
    assert put.calls[0]["method"] == "PUT" and put.calls[0]["body"] == b"abc" and put.calls[0]["headers"] == {"Content-Type": "video/mp4"}
    assert put.calls[0]["auth"] is False
    post = FakeClient([(204, b"", {}), (400, b"<Error><Code>EntityTooLarge</Code></Error>", {})])
    created = {"upload_url": "https://bucket.s3.ap-southeast-1.amazonaws.com/", "upload_method": "POST", "upload_fields": {"key": "inputs/a/b"}}
    assert portal_client.upload(post, created, b"abc", "video/mp4") == (True, 204)
    assert post.calls[0]["method"] == "POST" and post.calls[0]["headers"]["Content-Type"].startswith("multipart/form-data; boundary=")
    # Không gửi kèm token của portal tới S3: URL ký sẵn là quyền duy nhất.
    assert post.calls[0]["auth"] is False
    assert portal_client.upload(post, created, b"abcd", "video/mp4") == (False, 400)


def test_sign_in_uses_the_provider_the_portal_reports():
    local = FakeClient([(200, {"provider": "local"}, {}), (200, {"token": "session-token"}, {})])
    assert portal_client.sign_in(local, "a@example.com", "pw") == "session-token"
    assert local.calls[1]["path"] == "/api/auth/login" and local.calls[1]["body"] == {"email": "a@example.com", "password": "pw"}
    refused = FakeClient([(200, {"provider": "local"}, {}), (401, {"error": "invalid_credentials"}, {})])
    assert portal_client.sign_in(refused, "a@example.com", "wrong") is None

    cognito = FakeClient([(200, {"provider": "cognito", "region": "ap-southeast-1", "client_id": "client-1"}, {}),
                          (200, {"AuthenticationResult": {"IdToken": "id-token", "AccessToken": "access-token"}}, {})])
    assert portal_client.sign_in(cognito, "a@example.com", "pw") == "id-token"
    request = cognito.calls[1]
    assert request["path"] == "https://cognito-idp.ap-southeast-1.amazonaws.com/" and request["auth"] is False
    assert request["headers"]["X-Amz-Target"] == "AWSCognitoIdentityProviderService.InitiateAuth"
    assert b'"ClientId": "client-1"' in request["body"] and b"USER_PASSWORD_AUTH" in request["body"]
    challenge = FakeClient([(200, {"provider": "cognito", "region": "ap-southeast-1", "client_id": "client-1"}, {}),
                            (200, {"ChallengeName": "NEW_PASSWORD_REQUIRED"}, {})])
    assert portal_client.sign_in(challenge, "a@example.com", "pw") is None
    denied = FakeClient([(200, {"provider": "cognito", "region": "ap-southeast-1", "client_id": "client-1"}, {}),
                         (400, {"__type": "NotAuthorizedException"}, {})])
    assert portal_client.sign_in(denied, "a@example.com", "wrong") is None

    with pytest.raises(RuntimeError):
        portal_client.sign_in(FakeClient([(200, {"api_key": "firebase-web-key"}, {})]), "a@example.com", "pw")
    with pytest.raises(RuntimeError):
        portal_client.sign_in(FakeClient([(503, {"error": "auth_not_configured"}, {})]), "a@example.com", "pw")


def test_tampered_url_changes_only_the_signature():
    s3 = "https://bucket.s3.ap-southeast-1.amazonaws.com/outputs/a/b/video.mp4?versionId=v1&X-Amz-Signature=" + "ab12" * 16 + "&X-Amz-Expires=120"
    changed = portal_client.tampered(s3)
    assert changed != s3 and "X-Amz-Signature=" + "0" * 64 in changed and changed.endswith("&X-Amz-Expires=120") and "versionId=v1" in changed
    local = "/local-storage/read?ticket=abcdefghijklmnop"
    assert portal_client.tampered(local) != local and portal_client.tampered(local).startswith("/local-storage/read?ticket=abcdefghij")


def test_seed_refuses_a_dataset_that_does_not_match_its_manifest(tmp_path):
    import hashlib
    import json
    clips = []
    for number in range(1, 11):
        content = f"clip {number}".encode()
        (tmp_path / f"clip-{number:02d}.mp4").write_bytes(content)
        clips.append({"number": number, "file": f"clip-{number:02d}.mp4", "title": f"Synthetic clip {number:02d}",
                      "size_bytes": len(content), "sha256": hashlib.sha256(content).hexdigest(), "expected_duration_seconds": 1})
    (tmp_path / "manifest.json").write_text(json.dumps({"clips": clips}), encoding="utf-8")
    loaded = seed_remote.load_clips(tmp_path)
    assert [clip["number"] for clip in loaded] == list(range(1, 11)) and loaded[0]["content"] == b"clip 1"
    (tmp_path / "clip-03.mp4").write_bytes(b"clip X")  # cùng kích thước, khác nội dung
    with pytest.raises(ValueError, match="clip-03.mp4"):
        seed_remote.load_clips(tmp_path)
    (tmp_path / "manifest.json").write_text(json.dumps({"clips": clips[:9]}), encoding="utf-8")
    with pytest.raises(ValueError, match="ten clips"):
        seed_remote.load_clips(tmp_path)
