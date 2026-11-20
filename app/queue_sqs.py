"""Hàng đợi Amazon SQS, cùng giao diện với PgBroker/FileBroker (publish/receive/ack/dead_letter).

SQS giao at-least-once: message đã nhận sẽ ẩn `visibility` giây và tự hiện lại nếu worker chết trước khi ack.
Queue chính có redrive policy sang dead-letter queue (khai báo ở hạ tầng). Tính đúng-một-kết-quả vẫn do
lease + attempt ID của job trong PostgreSQL bảo đảm, không do hàng đợi.
"""

import json
import time
from uuid import UUID

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from app.queue_local import QueueError

VISIBILITY_SECONDS = 300
WAIT_SECONDS = 2


def sqs_client(region):
    return boto3.client("sqs", region_name=region, config=Config(connect_timeout=5, read_timeout=30, retries={"max_attempts": 3}))


class SqsBroker:
    def __init__(self, client, queue_url, dead_letter_url, visibility_seconds=VISIBILITY_SECONDS, wait_seconds=WAIT_SECONDS):
        self.client = client
        self.queue_url = queue_url
        self.dead_letter_url = dead_letter_url
        self.visibility = visibility_seconds
        self.wait = wait_seconds

    def call(self, operation, **values):
        try:
            return getattr(self.client, operation)(**values)
        except (BotoCoreError, ClientError):
            raise QueueError(f"sqs_{operation}_failed") from None

    def publish(self, operation_key, payload):
        body = json.dumps({"operation_key": str(UUID(str(operation_key))), "payload": payload})
        if len(body.encode()) > 4096:
            raise QueueError("message_too_large")
        self.call("send_message", QueueUrl=self.queue_url, MessageBody=body)

    def receive(self):
        # Long polling ngắn: hỏi mọi máy chủ SQS (short poll có thể bỏ sót) mà vòng lặp worker vẫn kịp relay outbox.
        response = self.call(
            "receive_message", QueueUrl=self.queue_url, MaxNumberOfMessages=1, WaitTimeSeconds=self.wait,
            VisibilityTimeout=self.visibility, MessageSystemAttributeNames=["ApproximateReceiveCount"],
        )
        messages = response.get("Messages") or []
        if not messages:
            return None
        message = messages[0]
        try:
            data = json.loads(message["Body"])
        except ValueError:
            data = {}
        if not isinstance(data, dict):
            data = {}
        return {"delivery_id": message["ReceiptHandle"], "operation_key": data.get("operation_key"), "payload": data.get("payload"),
                "deliveries": int(message.get("Attributes", {}).get("ApproximateReceiveCount", 1)),
                "body": message["Body"], "extended_at": time.monotonic()}

    def extend(self, delivery):
        """Heartbeat của worker gọi hàm này: giữ message ẩn chừng nào job còn chạy."""
        if time.monotonic() - delivery["extended_at"] < self.visibility / 3:
            return
        try:
            self.client.change_message_visibility(QueueUrl=self.queue_url, ReceiptHandle=delivery["delivery_id"], VisibilityTimeout=self.visibility)
        except (BotoCoreError, ClientError):
            # Không gia hạn được thì message chỉ bị giao lại; claim_job thấy job đang PROCESSING và bỏ qua.
            return
        delivery["extended_at"] = time.monotonic()

    def ack(self, delivery):
        self.call("delete_message", QueueUrl=self.queue_url, ReceiptHandle=delivery["delivery_id"])

    def dead_letter(self, delivery, reason):
        self.call("send_message", QueueUrl=self.dead_letter_url, MessageBody=delivery.get("body") or "{}",
                  MessageAttributes={"dead_reason": {"DataType": "String", "StringValue": str(reason)[:80]}})
        self.ack(delivery)

    def counts(self):
        def visible(url):
            attributes = self.call("get_queue_attributes", QueueUrl=url, AttributeNames=["ApproximateNumberOfMessages"])
            return int(attributes["Attributes"]["ApproximateNumberOfMessages"])
        return {"pending": visible(self.queue_url), "dead": visible(self.dead_letter_url)}
