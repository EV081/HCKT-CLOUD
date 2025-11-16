import json
import uuid
import os
import boto3

TABLE_EMPLEADOS_NAME = os.getenv("TABLE_EMPLEADOS", "TABLE_EMPLEADOS")

dynamodb = boto3.resource("dynamodb")
empleados_table = dynamodb.Table(TABLE_EMPLEADOS_NAME)

TIPOS_AREA = {"mantenimiento", "electricidad", "limpieza", "seguridad", "ti", "logistica", "otros"}
ESTADOS_VALIDOS = {"activo", "inactivo"}

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
    if rol not in {"personal_administrativo", "autoridad"}:
        return {
            "statusCode": 403,
            "body": json.dumps({"message": "No tienes permiso para crear empleados"})
        }

    body = _parse_body(event)
    nombre = body.get("nombre")
    tipo_area = body.get("tipo_area")
    estado = body.get("estado", "activo")
    contacto = body.get("contacto", {})

    if not nombre or not tipo_area:
        return {
            "statusCode": 400,
            "body": json.dumps({"message": "nombre y tipo_area son obligatorios"})
        }

    if tipo_area not in TIPOS_AREA:
        return {
            "statusCode": 400,
            "body": json.dumps({"message": "tipo_area inválido"})
        }

    if estado not in ESTADOS_VALIDOS:
        return {
            "statusCode": 400,
            "body": json.dumps({"message": "estado inválido"})
        }

    if contacto and not isinstance(contacto, dict):
        return {
            "statusCode": 400,
            "body": json.dumps({"message": "contacto debe ser un objeto"})
        }

    empleado = {
        "empleado_id": str(uuid.uuid4()),
        "nombre": nombre,
        "tipo_area": tipo_area,
        "estado": estado,
        "contacto": contacto if contacto else {}
    }

    try:
        empleados_table.put_item(Item=empleado)
    except Exception as e:
        return {
            "statusCode": 500,
            "body": json.dumps({"message": f"Error al crear empleado: {str(e)}"})
        }

    return {
        "statusCode": 201,
        "body": json.dumps({
            "message": "Empleado creado correctamente",
            "empleado": empleado
        })
    }
