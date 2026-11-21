"""Hàng đợi Azure Service Bus, cùng giao diện với PgBroker/FileBroker (publish/receive/ack/dead_letter).

Service Bus giao at-least-once: message đã nhận bị khoá (peek-lock) và tự hiện lại nếu worker chết trước khi ack.
Quá số lần giao của queue thì Service Bus tự chuyển message sang dead-letter queue có sẵn. Tính đúng-một-kết-quả
vẫn do lease + attempt ID của job trong PostgreSQL bảo đảm, không do hàng đợi.
"""

import json
from threading import Lock
import time
from uuid import UUID

from azure.core.exceptions import AzureError
from azure.servicebus import ServiceBusClient, ServiceBusMessage

from app.queue_local import QueueError

WAIT_SECONDS = 2
RENEW_SECONDS = 20


def servicebus_client(namespace):
    # Managed identity qua DefaultAzureCredential: không có connection string hay khoá SAS trong cấu hình.
    from azure.identity import DefaultAzureCredential
    return ServiceBusClient(f"{namespace}.servicebus.windows.net", credential=DefaultAzureCredential())


class ServiceBusBroker:
    def __init__(self, client, queue, wait_seconds=WAIT_SECONDS, renew_seconds=RENEW_SECONDS):
        self.client = client
        self.queue = queue
        self.wait = wait_seconds
        self.renew = renew_seconds
        self.sender = None
        self.receiver = None
        # Sender/receiver của SDK không an toàn cho nhiều luồng; API (Waitress) gọi publish từ nhiều luồng.
        self.lock = Lock()

    def call(self, label, action):
        try:
            return action()
        except AzureError:
            # Kết nối có thể đã hỏng: bỏ sender/receiver cũ để lần gọi sau mở lại.
            self.close_links()
            raise QueueError(f"servicebus_{label}_failed") from None

    def close_links(self):
        for link in (self.sender, self.receiver):
            try:
                if link is not None:
                    link.close()
            except AzureError:
                pass
        self.sender = self.receiver = None

    def close(self):
        with self.lock:
            self.close_links()
            try:
                self.client.close()
            except AzureError:
                pass

    def publish(self, operation_key, payload):
        key = str(UUID(str(operation_key)))
        body = json.dumps({"operation_key": key, "payload": payload})
        if len(body.encode()) > 4096:
            raise QueueError("message_too_large")
        with self.lock:
            if self.sender is None:
                self.sender = self.call("open", lambda: self.client.get_queue_sender(self.queue))
            self.call("send", lambda: self.sender.send_messages(ServiceBusMessage(body, message_id=key, content_type="application/json")))

    def receive(self):
        with self.lock:
            if self.receiver is None:
                self.receiver = self.call("open", lambda: self.client.get_queue_receiver(self.queue))
            messages = self.call("receive", lambda: self.receiver.receive_messages(max_message_count=1, max_wait_time=self.wait))
        if not messages:
            return None
        message = messages[0]
        try:
            data = json.loads(str(message))
        except ValueError:
            data = {}
        if not isinstance(data, dict):
            data = {}
        return {"delivery_id": message, "operation_key": data.get("operation_key"), "payload": data.get("payload"),
                "deliveries": message.delivery_count, "extended_at": time.monotonic()}

    def extend(self, delivery):
        """Heartbeat của worker gọi hàm này: gia hạn khoá của message chừng nào job còn chạy."""
        if time.monotonic() - delivery["extended_at"] < self.renew:
            return
        try:
            self.receiver.renew_message_lock(delivery["delivery_id"])
        except (AzureError, AttributeError):
            # Không gia hạn được thì message chỉ bị giao lại; claim_job thấy job đang PROCESSING và bỏ qua.
            return
        delivery["extended_at"] = time.monotonic()

    def ack(self, delivery):
        with self.lock:
            receiver = self.receiver
            if receiver is None:
                raise QueueError("servicebus_complete_failed")
            self.call("complete", lambda: receiver.complete_message(delivery["delivery_id"]))

    def dead_letter(self, delivery, reason):
        with self.lock:
            receiver = self.receiver
            if receiver is None:
                raise QueueError("servicebus_dead_letter_failed")
            self.call("dead_letter", lambda: receiver.dead_letter_message(delivery["delivery_id"], reason=str(reason)[:80]))
