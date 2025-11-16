import json
import os
import boto3
from boto3.dynamodb.conditions import Attr

TABLE_EMPLEADOS_NAME = os.getenv("TABLE_EMPLEADOS", "TABLE_EMPLEADOS")
CORS_HEADERS = {"Access-Control-Allow-Origin": "*"}

dynamodb = boto3.resource("dynamodb")
empleados_table = dynamodb.Table(TABLE_EMPLEADOS_NAME)

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
    if authorizer.get("rol") not in ROLES_PERMITIDOS:
        return {
            "statusCode": 403,
            "headers": CORS_HEADERS,
            "body": json.dumps({"message": "No tienes permiso para listar empleados"})
        }

    body = _parse_body(event)
    limit = body.get("limit") or body.get("size") or 10
    try:
        limit = max(1, min(int(limit), 50))
    except (TypeError, ValueError):
        limit = 10

    filtro_estado = body.get("estado")
    last_key = body.get("last_key")

    scan_kwargs = {"Limit": limit}
    if isinstance(last_key, dict) and "empleado_id" in last_key:
        scan_kwargs["ExclusiveStartKey"] = {"empleado_id": last_key["empleado_id"]}
    elif isinstance(last_key, str) and last_key:
        scan_kwargs["ExclusiveStartKey"] = {"empleado_id": last_key}

    if filtro_estado in {"activo", "inactivo"}:
        scan_kwargs["FilterExpression"] = Attr("estado").eq(filtro_estado)

    try:
        response = empleados_table.scan(**scan_kwargs)
    except Exception as e:
        return {
            "statusCode": 500,
            "headers": CORS_HEADERS,
            "body": json.dumps({"message": f"Error al listar empleados: {str(e)}"})
        }

    items = response.get("Items", [])
    last_evaluated = response.get("LastEvaluatedKey")
    return {
        "statusCode": 200,
        "headers": CORS_HEADERS,
        "body": json.dumps({
            "empleados": items,
            "count": len(items),
            "last_key": last_evaluated
        })
    }
