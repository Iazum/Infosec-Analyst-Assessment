"""
Orders API: Lambda proxy integration behind API Gateway (REST).

Routes
  POST /orders              create an order for the authenticated user
  GET  /orders              list the authenticated user's orders (max 50)
  GET  /orders/{orderId}    fetch one of the authenticated user's orders

DynamoDB table (env TABLE_NAME)
  Partition key: userId (String)   <- Cognito "sub" claim
  Sort key:      orderId (String)

Isolation: userId always comes from the verified JWT claims injected by the
Cognito authorizer, never from the request body or path, so users can only
see their own orders.
"""
import json
import logging
import os
import uuid
from datetime import datetime, timezone
from decimal import Decimal

import boto3
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

logger = logging.getLogger()
logger.setLevel(logging.INFO)

TABLE = boto3.resource("dynamodb").Table(os.environ["TABLE_NAME"])

HEADERS = {
    "Content-Type": "application/json",
    "X-Content-Type-Options": "nosniff",
    "Cache-Control": "no-store",
}

MAX_ITEM_LEN = 100
MAX_QTY = 1000


class _JSONEncoder(json.JSONEncoder):
    """DynamoDB returns numbers as Decimal; convert for JSON."""

    def default(self, o):
        if isinstance(o, Decimal):
            return int(o) if o % 1 == 0 else float(o)
        return super().default(o)


def _response(status, body):
    return {
        "statusCode": status,
        "headers": HEADERS,
        "body": json.dumps(body, cls=_JSONEncoder),
    }


def _user_id(event):
    authorizer = (event.get("requestContext") or {}).get("authorizer") or {}
    claims = authorizer.get("claims") or {}
    return claims.get("sub")


def _parse_order(event):
    """Return (order_fields, error_message)."""
    try:
        data = json.loads(event.get("body") or "{}")
    except json.JSONDecodeError:
        return None, "Body must be valid JSON"

    if not isinstance(data, dict):
        return None, "Body must be a JSON object"

    item = data.get("item")
    qty = data.get("qty")

    if not isinstance(item, str) or not (1 <= len(item.strip()) <= MAX_ITEM_LEN):
        return None, f"'item' must be a string of 1-{MAX_ITEM_LEN} characters"
    if isinstance(qty, bool) or not isinstance(qty, int) or not (1 <= qty <= MAX_QTY):
        return None, f"'qty' must be an integer between 1 and {MAX_QTY}"

    return {"item": item.strip(), "qty": qty}, None


def create_order(user_id, event):
    fields, error = _parse_order(event)
    if error:
        return _response(400, {"error": error})

    order = {
        "userId": user_id,
        "orderId": str(uuid.uuid4()),
        "item": fields["item"],
        "qty": fields["qty"],
        "status": "CREATED",
        "createdAt": datetime.now(timezone.utc).isoformat(),
    }
    TABLE.put_item(Item=order)
    logger.info(json.dumps({"event": "order_created", "orderId": order["orderId"]}))
    return _response(201, order)


def list_orders(user_id):
    result = TABLE.query(KeyConditionExpression=Key("userId").eq(user_id), Limit=50)
    items = result.get("Items", [])
    return _response(200, {"count": len(items), "orders": items})


def get_order(user_id, order_id):
    result = TABLE.get_item(Key={"userId": user_id, "orderId": order_id})
    item = result.get("Item")
    if not item:
        return _response(404, {"error": "Order not found"})
    return _response(200, item)


def lambda_handler(event, context):
    user_id = _user_id(event)
    if not user_id:
        # Should never happen behind the Cognito authorizer; fail closed.
        return _response(401, {"error": "Unauthorized"})

    method = event.get("httpMethod")
    resource = event.get("resource")

    try:
        if resource == "/orders" and method == "POST":
            return create_order(user_id, event)
        if resource == "/orders" and method == "GET":
            return list_orders(user_id)
        if resource == "/orders/{orderId}" and method == "GET":
            order_id = (event.get("pathParameters") or {}).get("orderId", "")
            return get_order(user_id, order_id)
        return _response(404, {"error": "Not found"})
    except ClientError:
        logger.exception("DynamoDB error")
        return _response(500, {"error": "Internal server error"})
    except Exception:
        logger.exception("Unhandled error")
        return _response(500, {"error": "Internal server error"})
