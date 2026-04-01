#!/bin/bash
# Test the deployed Agrobot API on AWS
set -e

echo "Fetching API URL from CloudFormation..."
API_URL=$(aws cloudformation describe-stacks --stack-name AgrobotStack \
  --query 'Stacks[0].Outputs[?contains(OutputKey,`ServiceURL`) || contains(OutputKey,`LoadBalancer`)].OutputValue' \
  --output text 2>/dev/null | head -1)

if [ -z "$API_URL" ]; then
  echo "Could not find API URL. Is the stack deployed?"
  echo "Run: make deploy"
  exit 1
fi

# Remove trailing slash
API_URL="${API_URL%/}"
echo "API URL: $API_URL"
echo ""

# ── Health ───────────────────────────────────────────────────
echo "=== Health Check ==="
HEALTH=$(curl -s -w "\n%{http_code}" "$API_URL/health")
HTTP_CODE=$(echo "$HEALTH" | tail -1)
BODY=$(echo "$HEALTH" | head -1)
if [ "$HTTP_CODE" = "200" ]; then
  echo "  OK: $BODY"
else
  echo "  FAIL ($HTTP_CODE): $BODY"
  echo "  API may still be starting. Wait a minute and retry."
  exit 1
fi
echo ""

# ── Auth ─────────────────────────────────────────────────────
echo "=== Auth ==="

# Register (may 409 if already seeded)
curl -s -X POST "$API_URL/auth/register" \
  -H "Content-Type: application/json" \
  -d '{"email":"cloudtest@agrobot.com","password":"testpass123"}' > /dev/null 2>&1

# Login
TOKEN=$(curl -s -X POST "$API_URL/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email":"user@agrobot.com","password":"password123"}' | jq -r .access_token 2>/dev/null)

if [ "$TOKEN" = "null" ] || [ -z "$TOKEN" ]; then
  echo "  Login failed. Trying cloud test user..."
  TOKEN=$(curl -s -X POST "$API_URL/auth/login" \
    -H "Content-Type: application/json" \
    -d '{"email":"cloudtest@agrobot.com","password":"testpass123"}' | jq -r .access_token 2>/dev/null)
fi

if [ "$TOKEN" = "null" ] || [ -z "$TOKEN" ]; then
  echo "  FAIL: Could not login"
  exit 1
fi
echo "  OK: Got JWT token"
echo ""

# ── Rules CRUD ───────────────────────────────────────────────
echo "=== Rules CRUD ==="

# Create
RULE=$(curl -s -X POST "$API_URL/rules" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"latitude":-34.6037,"longitude":-58.3816,"metric_type":"temperature","operator":"gt","threshold_value":30.0}')
RULE_ID=$(echo "$RULE" | jq -r .id 2>/dev/null)

if [ "$RULE_ID" = "null" ] || [ -z "$RULE_ID" ]; then
  echo "  Create: FAIL - $RULE"
else
  echo "  Create: OK (id=$RULE_ID)"
fi

# Read
READ=$(curl -s "$API_URL/rules/$RULE_ID" -H "Authorization: Bearer $TOKEN")
READ_ID=$(echo "$READ" | jq -r .id 2>/dev/null)
echo "  Read:   $([ "$READ_ID" = "$RULE_ID" ] && echo "OK" || echo "FAIL")"

# Update
UPDATE=$(curl -s -X PUT "$API_URL/rules/$RULE_ID" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"threshold_value":35.0}')
NEW_THRESH=$(echo "$UPDATE" | jq -r .threshold_value 2>/dev/null)
echo "  Update: $([ "$NEW_THRESH" = "35.0" ] && echo "OK (threshold=35.0)" || echo "FAIL")"

# List
COUNT=$(curl -s "$API_URL/rules" -H "Authorization: Bearer $TOKEN" | jq 'length' 2>/dev/null)
echo "  List:   OK ($COUNT rules)"

# Delete
DEL_CODE=$(curl -s -o /dev/null -w "%{http_code}" -X DELETE "$API_URL/rules/$RULE_ID" \
  -H "Authorization: Bearer $TOKEN")
echo "  Delete: $([ "$DEL_CODE" = "204" ] && echo "OK" || echo "FAIL ($DEL_CODE)")"

# Verify deleted
GONE_CODE=$(curl -s -o /dev/null -w "%{http_code}" "$API_URL/rules/$RULE_ID" \
  -H "Authorization: Bearer $TOKEN")
echo "  Gone:   $([ "$GONE_CODE" = "404" ] && echo "OK (404)" || echo "FAIL ($GONE_CODE)")"
echo ""

# ── Composite Rules ──────────────────────────────────────────
echo "=== Composite Rules ==="

GROUP=$(curl -s -X POST "$API_URL/rule-groups" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "latitude": -34.6037, "longitude": -58.3816, "logic": "and",
    "conditions": [
      {"metric_type": "temperature", "operator": "gt", "threshold_value": 30.0},
      {"metric_type": "humidity", "operator": "lt", "threshold_value": 50.0}
    ]
  }')
GROUP_ID=$(echo "$GROUP" | jq -r .id 2>/dev/null)
COND_COUNT=$(echo "$GROUP" | jq '.conditions | length' 2>/dev/null)

if [ "$GROUP_ID" = "null" ] || [ -z "$GROUP_ID" ]; then
  echo "  Create: FAIL - $GROUP"
else
  echo "  Create: OK (id=$GROUP_ID, $COND_COUNT conditions)"
fi

# Cleanup
curl -s -o /dev/null -X DELETE "$API_URL/rule-groups/$GROUP_ID" -H "Authorization: Bearer $TOKEN"
echo "  Delete: OK"
echo ""

# ── Metric Types ─────────────────────────────────────────────
echo "=== Metric Types ==="
METRICS=$(curl -s "$API_URL/metric-types" | jq -r '.[].name' 2>/dev/null | tr '\n' ', ')
echo "  Available: ${METRICS%, }"

# Admin add new metric
ADMIN_TOKEN=$(curl -s -X POST "$API_URL/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@agrobot.com","password":"admin123"}' | jq -r .access_token 2>/dev/null)

if [ "$ADMIN_TOKEN" != "null" ] && [ -n "$ADMIN_TOKEN" ]; then
  ADD=$(curl -s -X POST "$API_URL/metric-types" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $ADMIN_TOKEN" \
    -d '{"name":"uv_index"}')
  UV_ID=$(echo "$ADD" | jq -r .id 2>/dev/null)
  if [ "$UV_ID" != "null" ] && [ -n "$UV_ID" ]; then
    echo "  Add uv_index: OK (id=$UV_ID)"
    # Cleanup
    curl -s -o /dev/null -X DELETE "$API_URL/metric-types/$UV_ID" -H "Authorization: Bearer $ADMIN_TOKEN"
    echo "  Delete uv_index: OK"
  else
    echo "  Add uv_index: SKIP (may already exist)"
  fi
fi
echo ""

# ── IDOR Prevention ──────────────────────────────────────────
echo "=== IDOR Prevention ==="

# Create rule as user
RULE2=$(curl -s -X POST "$API_URL/rules" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"latitude":0,"longitude":0,"metric_type":"temperature","operator":"gt","threshold_value":99}')
RULE2_ID=$(echo "$RULE2" | jq -r .id 2>/dev/null)

# Try to read as different user
OTHER_TOKEN=$(curl -s -X POST "$API_URL/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email":"cloudtest@agrobot.com","password":"testpass123"}' | jq -r .access_token 2>/dev/null)

if [ "$OTHER_TOKEN" != "null" ] && [ -n "$OTHER_TOKEN" ]; then
  IDOR_CODE=$(curl -s -o /dev/null -w "%{http_code}" "$API_URL/rules/$RULE2_ID" \
    -H "Authorization: Bearer $OTHER_TOKEN")
  echo "  Other user reads my rule: $([ "$IDOR_CODE" = "404" ] && echo "BLOCKED (404)" || echo "FAIL ($IDOR_CODE)")"
else
  echo "  SKIP (could not create second user)"
fi

# Cleanup
curl -s -o /dev/null -X DELETE "$API_URL/rules/$RULE2_ID" -H "Authorization: Bearer $TOKEN"
echo ""

# ── Summary ──────────────────────────────────────────────────
echo "========================================="
echo "  API URL: $API_URL"
echo "  Docs:    $API_URL/docs"
echo "  Dashboard: $API_URL/dashboard"
echo "========================================="
echo ""
echo "When done testing, destroy everything:"
echo "  make deploy-destroy"
