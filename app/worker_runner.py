import json
from pathlib import Path
import subprocess
from uuid import UUID

from worker.transcode import MediaError


def run_container(source, output, attempt_id):
    attempt_id = UUID(str(attempt_id))
    name = "video-worker-" + attempt_id.hex
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    source = Path(source).resolve()
    arguments = [
        "docker", "run", "--rm", "--name", name,
        "--label", "videoportal.attempt=" + str(attempt_id),
        "--network", "none", "--read-only", "--cpus", "1", "--memory", "512m",
        "--pids-limit", "64", "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
        "--tmpfs", "/tmp:rw,noexec,nosuid,size=32m",
        "--mount", f"type=bind,source={source.parent},target=/input,readonly",
        "--mount", f"type=bind,source={output},target=/output",
        "video-worker:phase05", "/input/" + source.name, "/output",
    ]
    try:
        result = subprocess.run(arguments, capture_output=True, text=True, timeout=150)
    except subprocess.TimeoutExpired:
        # Chỉ dừng container có tên attempt UUID do lần gọi này vừa tạo.
        try:
            subprocess.run(["docker", "rm", "-f", name], capture_output=True, timeout=15)
        except (OSError, subprocess.TimeoutExpired):
            raise MediaError("container_cleanup_unconfirmed", retryable=True) from None
        raise MediaError("container_timeout", retryable=True) from None
    except OSError:
        raise MediaError("container_runtime_unavailable", retryable=True) from None
    return worker_result(result.returncode, result.stdout, output, "container")


def worker_result(returncode, stdout, output, kind):
    """Đổi mã thoát của `python -m worker.transcode` thành metadata hoặc MediaError (dùng chung cho Docker và native)."""
    if returncode == 0:
        try:
            return json.loads((Path(output) / "metadata.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            raise MediaError(kind + "_metadata_missing", retryable=True) from None
    if returncode in {2, 3}:
        try:
            failure = json.loads(stdout)
            code = failure["error"]
            if not isinstance(code, str) or not code.replace("_", "").isalnum() or len(code) > 80:
                raise ValueError
        except (ValueError, KeyError, TypeError):
            pass
        else:
            raise MediaError(code, retryable=returncode == 3)
    raise MediaError(kind + "_failed", retryable=True)
