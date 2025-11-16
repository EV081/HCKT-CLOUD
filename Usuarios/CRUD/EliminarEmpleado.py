import json
import os
import boto3
import uuid
from datetime import datetime, timezone
from botocore.exceptions import ClientError

TABLE_EMPLEADOS_NAME = os.getenv("TABLE_EMPLEADOS", "TABLE_EMPLEADOS")
TABLE_LOGS_NAME = os.getenv("TABLE_LOGS", "TABLE_LOGS")
CORS_HEADERS = {"Access-Control-Allow-Origin": "*"}

dynamodb = boto3.resource("dynamodb")
empleados_table = dynamodb.Table(TABLE_EMPLEADOS_NAME)
logs_table = dynamodb.Table(TABLE_LOGS_NAME)

ROLES_PERMITIDOS = {"personal_administrativo", "autoridad"}


def _parse_body(event):
    body = event.get("body", {})
    if isinstance(body, str):
        body = json.loads(body) if body.strip() else {}
    elif not isinstance(body, dict):
        body = {}
    return body


def _log_event(accion, usuario_autenticado, resultado, mensaje=None, detalles=None):
    """
    Registra un log en DynamoDB.
    No poner datos extremadamente sensibles, pero acá empleado_id está ok.
    """
    try:
        item = {
            "id": str(uuid.uuid4()),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "servicio": "empleados-eliminar",
            "accion": accion,
            "resultado": resultado,
        }

        if usuario_autenticado:
            item["usuario"] = usuario_autenticado.get("correo")
            item["rol"] = usuario_autenticado.get("rol")

        if mensaje:
            item["mensaje"] = mensaje

        if detalles:
            item["detalles"] = detalles

        logs_table.put_item(Item=item)
    except Exception:
        pass


def lambda_handler(event, context):
    authorizer = event.get("requestContext", {}).get("authorizer", {})
    usuario_autenticado = {
        "correo": authorizer.get("correo"),
        "rol": authorizer.get("rol"),
    } if authorizer else None

    if authorizer.get("rol") not in ROLES_PERMITIDOS:
        _log_event(
            accion="eliminar_empleado",
            usuario_autenticado=usuario_autenticado,
            resultado="error",
            mensaje="No tienes permiso para eliminar empleados",
            detalles={"rol_autenticado": authorizer.get("rol")}
        )
        return {
            "statusCode": 403,
            "headers": CORS_HEADERS,
            "body": json.dumps({"message": "No tienes permiso para eliminar empleados"})
        }

    body = _parse_body(event)
    empleado_id = body.get("empleado_id")
    if not empleado_id:
        _log_event(
            accion="eliminar_empleado",
            usuario_autenticado=usuario_autenticado,
            resultado="error",
            mensaje="empleado_id es obligatorio",
            detalles={}
        )
        return {
            "statusCode": 400,
            "headers": CORS_HEADERS,
            "body": json.dumps({"message": "empleado_id es obligatorio"})
        }

    try:
        resp = empleados_table.get_item(Key={"empleado_id": empleado_id})
    except ClientError as e:
        _log_event(
            accion="eliminar_empleado",
            usuario_autenticado=usuario_autenticado,
            resultado="error",
            mensaje="Error al obtener empleado",
            detalles={
                "empleado_id": empleado_id,
                "error": str(e)[:500]
            }
        )
        return {
            "statusCode": 500,
            "headers": CORS_HEADERS,
            "body": json.dumps({"message": f"Error al obtener empleado: {str(e)}"})
        }

    if "Item" not in resp:
        _log_event(
            accion="eliminar_empleado",
            usuario_autenticado=usuario_autenticado,
            resultado="error",
            mensaje="Empleado no encontrado",
            detalles={"empleado_id": empleado_id}
        )
        return {
            "statusCode": 404,
            "headers": CORS_HEADERS,
            "body": json.dumps({"message": "Empleado no encontrado"})
        }

    try:
        empleados_table.delete_item(Key={"empleado_id": empleado_id})
    except ClientError as e:
        _log_event(
            accion="eliminar_empleado",
            usuario_autenticado=usuario_autenticado,
            resultado="error",
            mensaje="Error al eliminar empleado",
            detalles={
                "empleado_id": empleado_id,
                "error": str(e)[:500]
            }
        )
        return {
            "statusCode": 500,
            "headers": CORS_HEADERS,
            "body": json.dumps({"message": f"Error al eliminar empleado: {str(e)}"})
        }

    _log_event(
        accion="eliminar_empleado",
        usuario_autenticado=usuario_autenticado,
        resultado="ok",
        mensaje="Empleado eliminado correctamente",
        detalles={"empleado_id": empleado_id}
    )

    return {
        "statusCode": 200,
        "headers": CORS_HEADERS,
        "body": json.dumps({"message": "Empleado eliminado correctamente"})
    }
