#!/usr/bin/env bash
# Evidence script: run from AWS CloudShell (or any shell with the AWS CLI + curl).
#
# Usage:
#   export API_URL="https://<api-id>.execute-api.<region>.amazonaws.com/prod"
#   export API_KEY="<api key value>"
#   export CLIENT_ID="<cognito app client id>"
#   export USERNAME="<test user>"
#   export PASSWORD="<test user password>"
#   export AWS_REGION="<region>"
#   bash run_tests.sh | tee results.txt
#
# Never commit real keys, tokens, or passwords. Redact them in any output you publish.

set -u
: "${API_URL:?}" "${API_KEY:?}" "${CLIENT_ID:?}" "${USERNAME:?}" "${PASSWORD:?}" "${AWS_REGION:?}"

line() { printf '\n==== %s ====\n' "$1"; }
code() { curl -s -o /dev/null -w '%{http_code}' "$@"; }

line "Get JWT (Cognito ID token)"
JWT=$(aws cognito-idp initiate-auth \
  --region "$AWS_REGION" \
  --auth-flow USER_PASSWORD_AUTH \
  --client-id "$CLIENT_ID" \
  --auth-parameters USERNAME="$USERNAME",PASSWORD="$PASSWORD" \
  --query 'AuthenticationResult.IdToken' --output text)
echo "token length: ${#JWT}"

line "TEST 1: no token -> expect 401"
echo "HTTP $(code -H "x-api-key: $API_KEY" "$API_URL/orders")"

line "TEST 2: valid JWT + API key, POST /orders -> expect 201"
curl -s -w '\nHTTP %{http_code}\n' -X POST "$API_URL/orders" \
  -H "Authorization: $JWT" -H "x-api-key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"item":"widget","qty":2}'

line "TEST 3: GET /orders -> expect 200"
curl -s -w '\nHTTP %{http_code}\n' "$API_URL/orders" \
  -H "Authorization: $JWT" -H "x-api-key: $API_KEY"

line "TEST 4: invalid body (qty=-5) -> expect 400 from request validation"
curl -s -w '\nHTTP %{http_code}\n' -X POST "$API_URL/orders" \
  -H "Authorization: $JWT" -H "x-api-key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"item":"widget","qty":-5}'

line "TEST 5: AI summarize with PII in text -> expect 200, redactions > 0"
curl -s -w '\nHTTP %{http_code}\n' -X POST "$API_URL/ai/summarize" \
  -H "Authorization: $JWT" -H "x-api-key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"text":"Please contact john.doe@example.com or call +254 712 345 678 about the Q3 supplier contract renewal. The contract covers delivery schedules, penalties for late shipments, and a price review in January."}'

line "TEST 6: SQLi payload -> expect 403 from WAF"
echo "HTTP $(code -G "$API_URL/orders" \
  --data-urlencode "q=' OR 1=1--" \
  -H "Authorization: $JWT" -H "x-api-key: $API_KEY")"

line "TEST 7: XSS payload -> expect 403 from WAF"
echo "HTTP $(code -G "$API_URL/orders" \
  --data-urlencode "q=<script>alert(1)</script>" \
  -H "Authorization: $JWT" -H "x-api-key: $API_KEY")"

line "TEST 8: burst of 40 requests -> expect some 429 (usage plan throttle)"
for i in $(seq 1 40); do
  code "$API_URL/orders" -H "Authorization: $JWT" -H "x-api-key: $API_KEY"
  printf ' '
done
echo
