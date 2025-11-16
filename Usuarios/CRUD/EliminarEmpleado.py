import json
import os
import boto3
from botocore.exceptions import ClientError

TABLE_EMPLEADOS_NAME = os.getenv("TABLE_EMPLEADOS", "TABLE_EMPLEADOS")

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
            "body": json.dumps({"message": "No tienes permiso para eliminar empleados"})
        }

    body = _parse_body(event)
    empleado_id = body.get("empleado_id")
    if not empleado_id:
        return {
            "statusCode": 400,
            "body": json.dumps({"message": "empleado_id es obligatorio"})
        }

    try:
        resp = empleados_table.get_item(Key={"empleado_id": empleado_id})
    except ClientError as e:
        return {
            "statusCode": 500,
            "body": json.dumps({"message": f"Error al obtener empleado: {str(e)}"})
        }

    if "Item" not in resp:
        return {
            "statusCode": 404,
            "body": json.dumps({"message": "Empleado no encontrado"})
        }

    try:
        empleados_table.delete_item(Key={"empleado_id": empleado_id})
    except ClientError as e:
        return {
            "statusCode": 500,
            "body": json.dumps({"message": f"Error al eliminar empleado: {str(e)}"})
        }

    return {
        "statusCode": 200,
        "body": json.dumps({"message": "Empleado eliminado correctamente"})
    }
