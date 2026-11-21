"""Kiểm thử phần dùng chung của scripts/smoke_test.py và scripts/seed_remote.py mà không cần máy chủ nào."""

from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import portal_client  # noqa: E402
import seed_remote  # noqa: E402
import acceptance_test  # noqa: E402
import load_test  # noqa: E402


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


def test_acceptance_profile_check_accepts_only_the_project_output_profile():
    video = {"codec_type": "video", "codec_name": "h264", "pix_fmt": "yuv420p", "width": 854, "height": 480}
    audio = {"codec_type": "audio", "codec_name": "aac"}
    container = {"format_name": "mov,mp4,m4a,3gp,3g2,mj2"}
    assert acceptance_test.matches_profile({"streams": [video, audio], "format": container})
    assert acceptance_test.matches_profile({"streams": [video], "format": container})  # nguồn không có âm thanh
    for change in ({"codec_name": "hevc"}, {"pix_fmt": "yuv444p"}, {"width": 1280}, {"height": 720}):
        assert not acceptance_test.matches_profile({"streams": [{**video, **change}, audio], "format": container})
    assert not acceptance_test.matches_profile({"streams": [video, {**audio, "codec_name": "mp3"}], "format": container})
    assert not acceptance_test.matches_profile({"streams": [video, video], "format": container})
    assert not acceptance_test.matches_profile({"streams": [video], "format": {"format_name": "matroska,webm"}})
    assert not acceptance_test.matches_profile({})  # ffprobe không đọc được file


def test_load_test_percentiles_are_real_samples_and_errors_are_counted():
    values = sorted(float(number) for number in range(1, 101))
    assert load_test.percentile(values, 50) == 50.0 and load_test.percentile(values, 95) == 95.0
    assert load_test.percentile([7.0], 95) == 7.0 and load_test.percentile([], 95) is None
    assert load_test.percentile([1.0, 2.0, 3.0], 95) == 3.0  # nearest rank: không nội suy ra số không có trong mẫu
    result = load_test.summary([("list", 200, 10.0), ("list", 200, 20.0), ("status", 503, 30.0), ("status", 0, 40.0)])
    assert result["requests"] == 4 and result["errors"] == 2 and result["error_rate_percent"] == 50.0
    assert result["p50_ms"] == 20.0 and result["p95_ms"] == 40.0 and result["max_ms"] == 40.0
