import json
import boto3
import os

TABLE_USUARIOS_NAME = os.getenv("TABLE_USUARIOS", "TABLE_USUARIOS")
CORS_HEADERS = {"Access-Control-Allow-Origin": "*"}

dynamodb = boto3.resource("dynamodb")
usuarios_table = dynamodb.Table(TABLE_USUARIOS_NAME)

ROLES_PERMITIDOS = {"personal_administrativo", "autoridad"}

def _parse_body(event):
    body = event.get("body", {})
    if isinstance(body, str):
        body = json.loads(body) if body.strip() else {}
    elif not isinstance(body, dict):
        body = {}
    return body

def lambda_handler(event, context):
    authorizer = event.get("requestContext", {}).get("authorizer", {})
    rol = authorizer.get("rol")
    if rol not in ROLES_PERMITIDOS:
        return {
            "statusCode": 403,
            "headers": CORS_HEADERS,
            "body": json.dumps({"message": "No tienes permiso para listar usuarios"})
        }

    body = _parse_body(event)
    limit = body.get("limit") or body.get("size") or 10
    try:
        limit = max(1, min(int(limit), 50))
    except (TypeError, ValueError):
        limit = 10

    last_key = body.get("last_key")
    scan_kwargs = {"Limit": limit}
    if isinstance(last_key, str) and last_key:
        scan_kwargs["ExclusiveStartKey"] = {"correo": last_key}

    try:
        response = usuarios_table.scan(**scan_kwargs)
    except Exception as e:
        return {
            "statusCode": 500,
            "headers": CORS_HEADERS,
            "body": json.dumps({"message": f"Error al listar usuarios: {str(e)}"})
        }

    items = response.get("Items", [])
    for item in items:
        item.pop("contrasena", None)

    last_evaluated = response.get("LastEvaluatedKey")
    return {
        "statusCode": 200,
        "headers": CORS_HEADERS,
        "body": json.dumps({
            "usuarios": items,
            "count": len(items),
            "last_key": last_evaluated.get("correo") if last_evaluated else None
        })
    }
