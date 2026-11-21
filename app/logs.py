"""Log có cấu trúc (JSON mỗi dòng), xoay vòng theo dung lượng và che thông tin nhạy cảm."""

from datetime import datetime, timezone
import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import re
import sys

SECRETS = [
    (re.compile(r"ticket=[^&\s\"']+"), "ticket=[redacted]"),
    (re.compile(r"(?i)bearer\s+[A-Za-z0-9._~+/=-]+"), "Bearer [redacted]"),
    (re.compile(r"(?i)(password|token|secret)(\"?\s*[:=]\s*\"?)[^\s\"',}]+"), r"\1\2[redacted]"),
]


def redact(text):
    for pattern, replacement in SECRETS:
        text = pattern.sub(replacement, text)
    return text


class JsonFormatter(logging.Formatter):
    def format(self, record):
        message = redact(record.getMessage())
        data = {"time": datetime.fromtimestamp(record.created, timezone.utc).isoformat(timespec="milliseconds"),
                "level": record.levelname, "logger": record.name}
        try:
            parsed = json.loads(message)
        except ValueError:
            parsed = None
        if isinstance(parsed, dict):
            data.update(parsed)
        else:
            data["message"] = message
        if record.exc_info:
            # Chỉ ghi loại lỗi; nội dung exception có thể chứa chuỗi kết nối.
            data["exception"] = record.exc_info[0].__name__
        return json.dumps(data, ensure_ascii=False)


def configure_logging(log_dir, name, megabytes=10, backups=5):
    """Ghi <name>.log (mọi mức) và <name>-error.log (chỉ lỗi). Không có LOG_DIR thì ghi ra stderr."""
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    for handler in list(root.handlers):
        root.removeHandler(handler)
    formatter = JsonFormatter()
    if log_dir:
        folder = Path(log_dir)
        folder.mkdir(parents=True, exist_ok=True)
        handlers = [RotatingFileHandler(folder / f"{name}.log", maxBytes=megabytes * 1_000_000, backupCount=backups, encoding="utf-8"),
                    RotatingFileHandler(folder / f"{name}-error.log", maxBytes=megabytes * 1_000_000, backupCount=backups, encoding="utf-8")]
        handlers[1].setLevel(logging.ERROR)
    else:
        handlers = [logging.StreamHandler(sys.stderr)]
    for handler in handlers:
        handler.setFormatter(formatter)
        root.addHandler(handler)
    logging.getLogger("waitress").setLevel(logging.WARNING)
    # SDK Azure ghi mỗi request HTTP và mỗi lần đổi trạng thái AMQP ở mức INFO, lấn át log của ứng dụng.
    logging.getLogger("azure").setLevel(logging.WARNING)
