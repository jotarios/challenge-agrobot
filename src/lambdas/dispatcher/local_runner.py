"""Local runner for the Notification Dispatcher.

Polls LocalStack SQS and invokes the Dispatcher handler logic directly.
Used for local development via Docker Compose.

Usage: python -m src.lambdas.dispatcher.local_runner
"""

import json
import logging
import time

import boto3

from src.shared.config import settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s [dispatcher] %(message)s")
logger = logging.getLogger(__name__)


def main():
    sqs = boto3.client(
        "sqs",
        region_name=settings.aws_region,
        endpoint_url=settings.aws_endpoint_url,
    )

    queue_url = settings.sqs_queue_url
    logger.info("Polling SQS queue: %s", queue_url)

    # Wait for queue to be ready
    while True:
        try:
            sqs.get_queue_attributes(QueueUrl=queue_url, AttributeNames=["QueueArn"])
            break
        except Exception:
            logger.info("Waiting for SQS queue...")
            time.sleep(2)

    logger.info("Queue ready. Starting to poll...")

    from src.lambdas.dispatcher.handler import _process_message

    while True:
        try:
            resp = sqs.receive_message(
                QueueUrl=queue_url,
                MaxNumberOfMessages=10,
                WaitTimeSeconds=5,
            )

            messages = resp.get("Messages", [])
            for msg in messages:
                try:
                    body = json.loads(msg["Body"])
                    result = _process_message(body)
                    logger.info("Message %s: %s", msg["MessageId"][:8], result)

                    # Delete on success
                    sqs.delete_message(
                        QueueUrl=queue_url,
                        ReceiptHandle=msg["ReceiptHandle"],
                    )
                except Exception as e:
                    logger.error("Failed to process message %s: %s", msg["MessageId"][:8], e)
                    # Don't delete — SQS will retry after visibility timeout

        except Exception as e:
            logger.error("Poll error: %s", e)
            time.sleep(5)


if __name__ == "__main__":
    main()
