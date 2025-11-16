import json
import os
import boto3
from botocore.exceptions import ClientError

TABLE_EMPLEADOS_NAME = os.getenv("TABLE_EMPLEADOS", "TABLE_EMPLEADOS")

dynamodb = boto3.resource("dynamodb")
empleados_table = dynamodb.Table(TABLE_EMPLEADOS_NAME)

TIPOS_AREA = {"mantenimiento", "electricidad", "limpieza", "seguridad", "ti", "logistica", "otros"}
ESTADOS_VALIDOS = {"activo", "inactivo"}
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
            "body": json.dumps({"message": "No tienes permiso para modificar empleados"})
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

    empleado = resp["Item"]
    hubo_cambios = False

    if "nombre" in body and body["nombre"]:
        empleado["nombre"] = body["nombre"]
        hubo_cambios = True

    if "tipo_area" in body:
        tipo_area = body["tipo_area"]
        if tipo_area not in TIPOS_AREA:
            return {
                "statusCode": 400,
                "body": json.dumps({"message": "tipo_area inválido"})
            }
        empleado["tipo_area"] = tipo_area
        hubo_cambios = True

    if "estado" in body:
        estado = body["estado"]
        if estado not in ESTADOS_VALIDOS:
            return {
                "statusCode": 400,
                "body": json.dumps({"message": "estado inválido"})
            }
        empleado["estado"] = estado
        hubo_cambios = True

    if "contacto" in body:
        contacto = body["contacto"]
        if contacto is not None and not isinstance(contacto, dict):
            return {
                "statusCode": 400,
                "body": json.dumps({"message": "contacto debe ser un objeto"})
            }
        empleado["contacto"] = contacto or {}
        hubo_cambios = True

    if not hubo_cambios:
        return {
            "statusCode": 400,
            "body": json.dumps({"message": "No hay cambios para aplicar"})
        }

    try:
        empleados_table.put_item(Item=empleado)
    except ClientError as e:
        return {
            "statusCode": 500,
            "body": json.dumps({"message": f"Error al actualizar empleado: {str(e)}"})
        }

    return {
        "statusCode": 200,
        "body": json.dumps({
            "message": "Empleado actualizado correctamente",
            "empleado": empleado
        })
    }
