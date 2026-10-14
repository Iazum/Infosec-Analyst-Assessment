"""
Summarize API: POST /ai/summarize

Thin API-facing Lambda. It validates input, then delegates to the LLM gateway
Lambda (the single controlled egress point for AI traffic) and maps the result
to an HTTP response. It never talks to a model directly.

Env vars
  LLM_GATEWAY_FUNCTION   name or ARN of the LLM gateway Lambda
"""
import json
import logging
import os

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger()
logger.setLevel(logging.INFO)

LAMBDA = boto3.client("lambda")
GATEWAY_FUNCTION = os.environ["LLM_GATEWAY_FUNCTION"]

MAX_CHARS = 5000
MIN_CHARS = 20

HEADERS = {
    "Content-Type": "application/json",
    "X-Content-Type-Options": "nosniff",
    "Cache-Control": "no-store",
}


def _response(status, body):
    return {"statusCode": status, "headers": HEADERS, "body": json.dumps(body)}


def _user_id(event):
    authorizer = (event.get("requestContext") or {}).get("authorizer") or {}
    return (authorizer.get("claims") or {}).get("sub")


def lambda_handler(event, context):
    user_id = _user_id(event)
    if not user_id:
        return _response(401, {"error": "Unauthorized"})

    try:
        data = json.loads(event.get("body") or "{}")
    except json.JSONDecodeError:
        return _response(400, {"error": "Body must be valid JSON"})

    text = data.get("text") if isinstance(data, dict) else None
    if not isinstance(text, str) or not (MIN_CHARS <= len(text.strip()) <= MAX_CHARS):
        return _response(
            400, {"error": f"'text' must be a string of {MIN_CHARS}-{MAX_CHARS} characters"}
        )

    payload = {"userId": user_id, "task": "summarize", "text": text.strip()}

    try:
        invoke = LAMBDA.invoke(
            FunctionName=GATEWAY_FUNCTION,
            InvocationType="RequestResponse",
            Payload=json.dumps(payload).encode("utf-8"),
        )
        result = json.loads(invoke["Payload"].read())
    except ClientError:
        logger.exception("Could not invoke LLM gateway")
        return _response(502, {"error": "AI service unavailable"})

    if invoke.get("FunctionError"):
        logger.error("LLM gateway returned a function error")
        return _response(502, {"error": "AI service error"})

    status = result.get("statusCode", 502)
    body = result.get("body", {})

    if status == 200:
        return _response(
            200,
            {
                "summary": body.get("summary"),
                "model": body.get("model"),
                "redactions": body.get("redactions", 0),
            },
        )
    if status == 429:
        return _response(429, {"error": "Daily AI quota exceeded. Try again tomorrow."})
    if 400 <= status < 500:
        return _response(status, {"error": body.get("error", "Bad request")})

    return _response(502, {"error": "AI service error"})
