#!/bin/bash
# Run the DB-only simulator as a one-off ECS task against cloud RDS.
# DMS picks up the inserts via CDC.
set -e

SCENARIO=${1:-NORMAL}
DURATION=${2:-30}
EVENTS=${3:-100}

echo "Fetching cluster and task info..."

CLUSTER=$(aws ecs list-clusters --query 'clusterArns[0]' --output text)
SERVICE=$(aws ecs list-services --cluster "$CLUSTER" --query 'serviceArns[0]' --output text)
TASK_DEF=$(aws ecs describe-services --cluster "$CLUSTER" --services "$SERVICE" \
  --query 'services[0].taskDefinition' --output text)

# Get VPC config from a running task
RUNNING_TASK=$(aws ecs list-tasks --cluster "$CLUSTER" --desired-status RUNNING --query 'taskArns[0]' --output text)
SUBNETS=$(aws ecs describe-tasks --cluster "$CLUSTER" --tasks "$RUNNING_TASK" \
  --query 'tasks[0].attachments[0].details[?name==`subnetId`].value' --output text)
SG=$(aws ecs describe-tasks --cluster "$CLUSTER" --tasks "$RUNNING_TASK" \
  --query 'tasks[0].attachments[0].details[?name==`securityGroupId`].value[]' --output text | head -1)

# Get container name
CONTAINER=$(aws ecs describe-task-definition --task-definition "$TASK_DEF" \
  --query 'taskDefinition.containerDefinitions[0].name' --output text)

# Build override JSON
if [ "$SCENARIO" = "SEVERE_STORM" ]; then
  OVERRIDE="{\"containerOverrides\":[{\"name\":\"$CONTAINER\",\"command\":[\"python\",\"-m\",\"simulator.db_only\",\"--scenario\",\"$SCENARIO\",\"--events\",\"$EVENTS\"]}]}"
else
  OVERRIDE="{\"containerOverrides\":[{\"name\":\"$CONTAINER\",\"command\":[\"python\",\"-m\",\"simulator.db_only\",\"--scenario\",\"$SCENARIO\",\"--duration\",\"$DURATION\"]}]}"
fi

echo "Cluster: $(echo $CLUSTER | rev | cut -d'/' -f1 | rev)"
echo "Scenario: $SCENARIO"
[ "$SCENARIO" = "SEVERE_STORM" ] && echo "Events: $EVENTS" || echo "Duration: ${DURATION}s"
echo ""
echo "Running ECS task..."

TASK_ARN=$(aws ecs run-task \
  --cluster "$CLUSTER" \
  --task-definition "$TASK_DEF" \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[$SUBNETS],securityGroups=[$SG],assignPublicIp=DISABLED}" \
  --overrides "$OVERRIDE" \
  --query 'tasks[0].taskArn' --output text)

TASK_ID=$(echo "$TASK_ARN" | rev | cut -d'/' -f1 | rev)
echo "Task: $TASK_ID"
echo ""

# Get log group info
LOG_GROUP=$(aws ecs describe-task-definition --task-definition "$TASK_DEF" \
  --query 'taskDefinition.containerDefinitions[0].logConfiguration.options."awslogs-group"' --output text)

echo "Waiting for task to start..."
aws ecs wait tasks-running --cluster "$CLUSTER" --tasks "$TASK_ARN" 2>/dev/null || true

echo "Tailing logs (Ctrl+C to stop, task keeps running)..."
echo ""
aws logs tail "$LOG_GROUP" --follow --since 1m 2>/dev/null || \
  echo "Could not tail logs. Check CloudWatch: $LOG_GROUP"
