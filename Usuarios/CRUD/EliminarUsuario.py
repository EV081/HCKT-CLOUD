import json
import boto3
import os
import uuid
from datetime import datetime, timezone

TABLE_USUARIOS_NAME = os.getenv("TABLE_USUARIOS", "TABLE_USUARIOS")
TABLE_LOGS_NAME = os.getenv("TABLE_LOGS", "TABLE_LOGS")  
CORS_HEADERS = {"Access-Control-Allow-Origin": "*"}

dynamodb = boto3.resource("dynamodb")
usuarios_table = dynamodb.Table(TABLE_USUARIOS_NAME)
logs_table = dynamodb.Table(TABLE_LOGS_NAME)


def _parse_body(event):
    body = {}
    if isinstance(event, dict) and "body" in event:
        raw_body = event.get("body")
        if isinstance(raw_body, str):
            body = json.loads(raw_body) if raw_body else {}
        elif isinstance(raw_body, dict):
            body = raw_body
    elif isinstance(event, dict):
        body = event
    elif isinstance(event, str):
        body = json.loads(event)
    return body if isinstance(body, dict) else {}


def _log_event(accion, usuario_autenticado, resultado, mensaje=None, detalles=None):
    """
    Registra un log en DynamoDB.
    No poner datos extremadamente sensibles; acá correos y roles están ok.
    """
    try:
        item = {
            "id": str(uuid.uuid4()),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "servicio": "usuarios-eliminar",
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
    if not authorizer:
        _log_event(
            accion="eliminar_usuario",
            usuario_autenticado=None,
            resultado="error",
            mensaje="Token requerido",
            detalles={"motivo": "sin_authorizer"}
        )
        return {
            "statusCode": 401,
            "headers": CORS_HEADERS,
            "body": json.dumps({"message": "Token requerido"})
        }

    usuario_autenticado = {
        "correo": authorizer.get("correo"),
        "rol": authorizer.get("rol")
    }

    body = _parse_body(event)

    correo_a_eliminar = body.get("correo")
    if not correo_a_eliminar:
        _log_event(
            accion="eliminar_usuario",
            usuario_autenticado=usuario_autenticado,
            resultado="error",
            mensaje="correo es obligatorio",
            detalles={}
        )
        return {
            "statusCode": 400,
            "headers": CORS_HEADERS,
            "body": json.dumps({"message": "correo es obligatorio"})
        }

    try:
        resp = usuarios_table.get_item(Key={"correo": correo_a_eliminar})
    except Exception as e:
        _log_event(
            accion="eliminar_usuario",
            usuario_autenticado=usuario_autenticado,
            resultado="error",
            mensaje="Error al obtener usuario",
            detalles={
                "correo_a_eliminar": correo_a_eliminar,
                "error": str(e)[:500]
            }
        )
        return {
            "statusCode": 500,
            "headers": CORS_HEADERS,
            "body": json.dumps({"message": f"Error al obtener usuario: {str(e)}"})
        }

    if "Item" not in resp:
        _log_event(
            accion="eliminar_usuario",
            usuario_autenticado=usuario_autenticado,
            resultado="error",
            mensaje="Usuario no encontrado",
            detalles={"correo_a_eliminar": correo_a_eliminar}
        )
        return {
            "statusCode": 404,
            "headers": CORS_HEADERS,
            "body": json.dumps({"message": "Usuario no encontrado"})
        }

    usuario_a_eliminar = resp["Item"]
    rol_a_eliminar = usuario_a_eliminar.get("rol", "estudiante")

    es_mismo_usuario = usuario_autenticado["correo"] == correo_a_eliminar
    rol_solicitante = usuario_autenticado["rol"]

    if es_mismo_usuario:
        permiso_ok = True
    elif rol_solicitante == "autoridad":
        permiso_ok = True
    elif rol_solicitante == "personal_administrativo":
        if rol_a_eliminar != "estudiante":
            _log_event(
                accion="eliminar_usuario",
                usuario_autenticado=usuario_autenticado,
                resultado="error",
                mensaje="Solo puedes eliminar estudiantes o tu propia cuenta",
                detalles={
                    "correo_a_eliminar": correo_a_eliminar,
                    "rol_a_eliminar": rol_a_eliminar
                }
            )
            return {
                "statusCode": 403,
                "headers": CORS_HEADERS,
                "body": json.dumps({"message": "Solo puedes eliminar estudiantes o tu propia cuenta"})
            }
        permiso_ok = True
    else:
        _log_event(
            accion="eliminar_usuario",
            usuario_autenticado=usuario_autenticado,
            resultado="error",
            mensaje="No tienes permiso para eliminar este usuario",
            detalles={
                "correo_a_eliminar": correo_a_eliminar,
                "rol_solicitante": rol_solicitante,
                "rol_a_eliminar": rol_a_eliminar
            }
        )
        return {
            "statusCode": 403,
            "headers": CORS_HEADERS,
            "body": json.dumps({"message": "No tienes permiso para eliminar este usuario"})
        }

    if not permiso_ok:
        _log_event(
            accion="eliminar_usuario",
            usuario_autenticado=usuario_autenticado,
            resultado="error",
            mensaje="Permiso no concedido por regla desconocida",
            detalles={"correo_a_eliminar": correo_a_eliminar}
        )
        return {
            "statusCode": 403,
            "headers": CORS_HEADERS,
            "body": json.dumps({"message": "No tienes permiso para eliminar este usuario"})
        }

    try:
        usuarios_table.delete_item(Key={"correo": correo_a_eliminar})
    except Exception as e:
        _log_event(
            accion="eliminar_usuario",
            usuario_autenticado=usuario_autenticado,
            resultado="error",
            mensaje="Error al eliminar usuario",
            detalles={
                "correo_a_eliminar": correo_a_eliminar,
                "error": str(e)[:500]
            }
        )
        return {
            "statusCode": 500,
            "headers": CORS_HEADERS,
            "body": json.dumps({"message": f"Error al eliminar usuario: {str(e)}"})
        }

    _log_event(
        accion="eliminar_usuario",
        usuario_autenticado=usuario_autenticado,
        resultado="ok",
        mensaje="Usuario eliminado correctamente",
        detalles={
            "correo_a_eliminar": correo_a_eliminar,
            "rol_a_eliminar": rol_a_eliminar
        }
    )

    return {
        "statusCode": 200,
        "headers": CORS_HEADERS,
        "body": json.dumps({"message": "Usuario eliminado correctamente"})
    }
