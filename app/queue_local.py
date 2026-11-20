"""Local durable delivery files; never a production Pub/Sub substitute."""

import json
import os
from pathlib import Path
import time
from uuid import UUID, uuid4


class QueueError(Exception):
    pass


def require_local_runtime():
    if os.getenv("K_SERVICE") or os.getenv("APP_ENV", "local") != "local":
        raise RuntimeError("Local queue/storage is not allowed in production")


class FileBroker:
    def __init__(self, root):
        require_local_runtime()
        self.root = Path(root).resolve()
        self.pending = self.root / "pending"
        self.dead = self.root / "dead"
        self.pending.mkdir(parents=True, exist_ok=True)
        self.dead.mkdir(parents=True, exist_ok=True)

    def publish(self, operation_key, payload):
        operation_key = str(UUID(str(operation_key)))
        content = json.dumps({"operation_key": operation_key, "payload": payload})
        if len(content.encode()) > 4096:
            raise QueueError("message_too_large")
        delivery_id = f"{time.time_ns()}-{uuid4().hex}"
        temporary = self.pending / (delivery_id + ".tmp")
        try:
            with temporary.open("x", encoding="utf-8") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.pending / (delivery_id + ".json"))
        except OSError:
            raise QueueError("local_publish_failed") from None
        finally:
            temporary.unlink(missing_ok=True)

    def receive(self):
        for path in sorted(self.pending.glob("*.json")):
            try:
                if path.stat().st_size > 4096:
                    data = {}
                else:
                    data = json.loads(path.read_text(encoding="utf-8"))
                if not isinstance(data, dict):
                    data = {}
                return {**data, "delivery_id": path.stem}
            except FileNotFoundError:
                continue
            except (ValueError, UnicodeError):
                return {"delivery_id": path.stem}
        return None

    def delivery_path(self, delivery_id):
        path = (self.pending / (delivery_id + ".json")).resolve()
        if path.parent != self.pending:
            raise QueueError("invalid_delivery_id")
        return path

    def ack(self, delivery):
        self.delivery_path(delivery["delivery_id"]).unlink(missing_ok=True)

    def dead_letter(self, delivery, reason):
        path = self.delivery_path(delivery["delivery_id"])
        (self.dead / path.name).write_text(json.dumps({"error": reason}), encoding="utf-8")
        path.unlink(missing_ok=True)
