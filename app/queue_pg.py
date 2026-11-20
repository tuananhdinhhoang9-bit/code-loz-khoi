"""Hàng đợi bền trong PostgreSQL, cùng giao diện với FileBroker (publish/receive/ack/dead_letter).

Giao at-least-once: message đã nhận sẽ ẩn trong VISIBILITY_SECONDS; nếu worker chết trước khi ack,
message tự hiện lại. Tính đúng-một-kết-quả do lease + attempt ID của job bảo đảm, không do hàng đợi.
"""

from datetime import timedelta
import json
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.models import QueueMessage
from app.queue_local import QueueError

VISIBILITY_SECONDS = 300
MAX_DELIVERIES = 10


def make_broker(app, engine):
    """Hàng đợi theo cấu hình: bảng PostgreSQL (mặc định, VPS/local) hoặc Amazon SQS (AWS)."""
    if app.config.get("QUEUE_BACKEND") == "sqs":
        from app.queue_sqs import SqsBroker, sqs_client
        return SqsBroker(sqs_client(app.config["AWS_REGION"]), app.config["SQS_QUEUE_URL"], app.config["SQS_DEAD_LETTER_URL"])
    return PgBroker(engine)


class PgBroker:
    def __init__(self, engine, visibility_seconds=VISIBILITY_SECONDS):
        self.engine = engine
        self.visibility = timedelta(seconds=visibility_seconds)

    def publish(self, operation_key, payload):
        operation_key = UUID(str(operation_key))
        if len(json.dumps(payload).encode()) > 4096:
            raise QueueError("message_too_large")
        try:
            with Session(self.engine) as session, session.begin():
                now = session.scalar(select(func.clock_timestamp()))
                session.add(QueueMessage(operation_key=operation_key, payload_json=payload, created_at=now, visible_at=now))
        except SQLAlchemyError:
            raise QueueError("queue_publish_failed") from None

    def receive(self):
        with Session(self.engine) as session, session.begin():
            now = session.scalar(select(func.clock_timestamp()))
            # SKIP LOCKED: hai worker không bao giờ cùng nhận một message. Mỗi lần chỉ khoá đúng một dòng,
            # để receiver chạy song song lấy được dòng kế tiếp thay vì thấy cả lô đang bị khoá và ra về tay trắng.
            for _ in range(5):
                message = session.scalars(
                    select(QueueMessage).where(QueueMessage.dead_at.is_(None), QueueMessage.visible_at <= now)
                    .order_by(QueueMessage.id).limit(1).with_for_update(skip_locked=True)
                ).first()
                if message is None:
                    return None
                if message.deliveries >= MAX_DELIVERIES:
                    # Đánh dấu chết rồi xét dòng kế tiếp trong cùng transaction (tối đa 5 dòng mỗi lần gọi).
                    message.dead_at, message.dead_reason = now, "delivery_exhausted"
                    continue
                message.deliveries += 1
                message.visible_at = now + self.visibility
                return {"delivery_id": str(message.id), "operation_key": str(message.operation_key),
                        "payload": message.payload_json, "deliveries": message.deliveries}
        return None

    def ack(self, delivery):
        with Session(self.engine) as session, session.begin():
            session.execute(delete(QueueMessage).where(QueueMessage.id == int(delivery["delivery_id"])))

    def dead_letter(self, delivery, reason):
        with Session(self.engine) as session, session.begin():
            message = session.get(QueueMessage, int(delivery["delivery_id"]), with_for_update=True)
            if message is not None:
                message.dead_at = session.scalar(select(func.clock_timestamp()))
                message.dead_reason = str(reason)[:80]

    def counts(self):
        with Session(self.engine) as session:
            dead = session.scalar(select(func.count()).select_from(QueueMessage).where(QueueMessage.dead_at.is_not(None)))
            total = session.scalar(select(func.count()).select_from(QueueMessage))
        return {"pending": total - dead, "dead": dead}
