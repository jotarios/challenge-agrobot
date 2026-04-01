#!/bin/bash
# Initialize LocalStack resources for local development
# Safe to re-run — skips resources that already exist

AWS="aws --endpoint-url=http://localhost:4566 --region us-east-1 --no-sign-request"

echo "Creating Kinesis stream..."
$AWS kinesis describe-stream --stream-name weather-events >/dev/null 2>&1 \
  || $AWS kinesis create-stream --stream-name weather-events --shard-count 2

echo "Creating SQS queues..."
$AWS sqs get-queue-url --queue-name agrobot-alerts-dlq >/dev/null 2>&1 \
  || $AWS sqs create-queue --queue-name agrobot-alerts-dlq

DLQ_ARN=$($AWS sqs get-queue-attributes \
  --queue-url http://localhost:4566/000000000000/agrobot-alerts-dlq \
  --attribute-names QueueArn --query 'Attributes.QueueArn' --output text)

$AWS sqs get-queue-url --queue-name agrobot-alerts >/dev/null 2>&1 \
  || $AWS sqs create-queue --queue-name agrobot-alerts \
    --attributes '{
      "RedrivePolicy": "{\"deadLetterTargetArn\":\"'"$DLQ_ARN"'\",\"maxReceiveCount\":\"3\"}",
      "VisibilityTimeout": "60"
    }'

echo "Creating Secrets Manager secret for JWT..."
$AWS secretsmanager describe-secret --secret-id agrobot/jwt-secret >/dev/null 2>&1 \
  || $AWS secretsmanager create-secret --name agrobot/jwt-secret --secret-string "dev-secret-change-in-production"

echo "LocalStack initialization complete!"
