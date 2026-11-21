"""Kiểm thử phần dùng chung của scripts/smoke_test.py và scripts/seed_remote.py mà không cần máy chủ nào."""

from pathlib import Path
import sys

import pytest

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


def test_upload_sends_the_headers_the_server_asked_for():
    local = FakeClient([(201, b"", {})])
    created = {"upload_url": "/local-storage/upload?ticket=t", "upload_method": "PUT", "upload_headers": {"Content-Type": "video/mp4"}}
    assert portal_client.upload(local, created, b"abc", "video/quicktime") == (True, 201)
    assert local.calls[0]["method"] == "PUT" and local.calls[0]["body"] == b"abc" and local.calls[0]["headers"] == {"Content-Type": "video/mp4"}
    assert local.calls[0]["auth"] is False
    blob = FakeClient([(201, b"", {}), (403, b"<Error><Code>AuthenticationFailed</Code></Error>", {})])
    created = {"upload_url": "https://account.blob.core.windows.net/media/inputs/a/b?sp=c&sig=abc", "upload_method": "PUT",
               "upload_headers": {"x-ms-blob-type": "BlockBlob", "Content-Type": "video/mp4"}}
    assert portal_client.upload(blob, created, b"abc", "video/mp4") == (True, 201)
    assert blob.calls[0]["method"] == "PUT" and blob.calls[0]["headers"] == {"x-ms-blob-type": "BlockBlob", "Content-Type": "video/mp4"}
    # Không gửi kèm token của portal tới Blob Storage: SAS là quyền duy nhất.
    assert blob.calls[0]["auth"] is False
    assert portal_client.upload(blob, created, b"abcd", "video/mp4") == (False, 403)
    # Máy chủ cũ không trả upload_headers: vẫn gửi Content-Type của file.
    old = FakeClient([(201, b"", {})])
    portal_client.upload(old, {"upload_url": "/local-storage/upload?ticket=t"}, b"abc", "video/webm")
    assert old.calls[0]["headers"] == {"Content-Type": "video/webm"}


def test_sign_in_uses_the_provider_the_portal_reports(monkeypatch):
    local = FakeClient([(200, {"provider": "local"}, {}), (200, {"token": "session-token"}, {})])
    assert portal_client.sign_in(local, "a@example.com", "pw") == "session-token"
    assert local.calls[1]["path"] == "/api/auth/login" and local.calls[1]["body"] == {"email": "a@example.com", "password": "pw"}
    refused = FakeClient([(200, {"provider": "local"}, {}), (401, {"error": "invalid_credentials"}, {})])
    assert portal_client.sign_in(refused, "a@example.com", "wrong") is None

    # OIDC cần trình duyệt: script chỉ nhận ID token có sẵn trong biến môi trường và không gửi mật khẩu đi đâu.
    reply = (200, {"provider": "oidc", "client_id": "client-1", "authorize_url": "https://login.example.test/authorize",
                   "token_url": "https://login.example.test/token"}, {})
    monkeypatch.setenv("PORTAL_ID_TOKEN", " id-token-from-the-browser ")
    oidc = FakeClient([reply])
    assert portal_client.sign_in(oidc, "a@example.com", "pw") == "id-token-from-the-browser"
    assert len(oidc.calls) == 1
    monkeypatch.delenv("PORTAL_ID_TOKEN")
    with pytest.raises(RuntimeError, match="PORTAL_ID_TOKEN"):
        portal_client.sign_in(FakeClient([reply]), "a@example.com", "pw")

    with pytest.raises(RuntimeError):
        portal_client.sign_in(FakeClient([(200, {"api_key": "firebase-web-key"}, {})]), "a@example.com", "pw")
    with pytest.raises(RuntimeError):
        portal_client.sign_in(FakeClient([(503, {"error": "auth_not_configured"}, {})]), "a@example.com", "pw")


def test_tampered_url_changes_only_the_signature():
    sas = "https://account.blob.core.windows.net/media/outputs/a/b/video.mp4?versionid=v1&se=2026-01-01T00%3A02%3A00Z&sp=r&sr=bv&sig=q1w2e3r4%2Bt5%3D&rsct=video/mp4"
    changed = portal_client.tampered(sas)
    assert changed != sas and "&sig=" + "A" * 43 + "%3D&rsct=video/mp4" in changed
    assert changed.split("&sig=")[0] == sas.split("&sig=")[0]
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
