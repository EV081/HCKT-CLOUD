import json
import boto3
import os
import uuid
from datetime import datetime, timezone

CORS_HEADERS = { "Access-Control-Allow-Origin": "*" }
TABLE_USUARIOS_NAME = os.getenv("TABLE_USUARIOS", "TABLE_USUARIOS")
TABLE_LOGS_NAME = os.getenv("TABLE_LOGS", "TABLE_LOGS") 

dynamodb = boto3.resource("dynamodb")
usuarios_table = dynamodb.Table(TABLE_USUARIOS_NAME)
logs_table = dynamodb.Table(TABLE_LOGS_NAME) 


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
    IMPORTANTE: no poner contraseñas ni datos sensibles en 'detalles'.
    """
    try:
        item = {
            "id": str(uuid.uuid4()),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "servicio": "usuarios-cambiar-contrasena",
            "accion": accion,
            "resultado": resultado,
        }

        if usuario_autenticado:
            item["usuario"] = usuario_autenticado.get("correo")
            item["rol"] = usuario_autenticado.get("rol")

        if mensaje:
            item["mensaje"] = mensaje

        if detalles:
            if "contrasena_actual" in detalles:
                detalles["contrasena_actual"] = "***"
            if "nueva_contrasena" in detalles:
                detalles["nueva_contrasena"] = "***"
            item["detalles"] = detalles

        logs_table.put_item(Item=item)
    except Exception:
        pass


def lambda_handler(event, context):
    body = _parse_body(event)
    authorizer = event.get("requestContext", {}).get("authorizer", {})

    if not authorizer:
        _log_event(
            accion="cambiar_contrasena",
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

    correo_objetivo = body.get("correo", usuario_autenticado["correo"])
    if not correo_objetivo:
        _log_event(
            accion="cambiar_contrasena",
            usuario_autenticado=usuario_autenticado,
            resultado="error",
            mensaje="correo es obligatorio",
            detalles={"correo_objetivo": None}
        )
        return {
            "statusCode": 400,
            "headers": CORS_HEADERS,
            "body": json.dumps({"message": "correo es obligatorio"})
        }

    nueva_contrasena = body.get("nueva_contrasena")
    if not nueva_contrasena or len(nueva_contrasena) < 6:
        _log_event(
            accion="cambiar_contrasena",
            usuario_autenticado=usuario_autenticado,
            resultado="error",
            mensaje="La nueva contraseña debe tener al menos 6 caracteres",
            detalles={"correo_objetivo": correo_objetivo}
        )
        return {
            "statusCode": 400,
            "headers": CORS_HEADERS,
            "body": json.dumps({"message": "La nueva contraseña debe tener al menos 6 caracteres"})
        }

    requiere_actual = True
    if usuario_autenticado["rol"] == "autoridad" and correo_objetivo != usuario_autenticado["correo"]:
        requiere_actual = False

    contrasena_actual = body.get("contrasena_actual") if requiere_actual else None

    try:
        resp = usuarios_table.get_item(Key={"correo": correo_objetivo})
    except Exception as e:
        _log_event(
            accion="cambiar_contrasena",
            usuario_autenticado=usuario_autenticado,
            resultado="error",
            mensaje="Error al obtener usuario",
            detalles={
                "correo_objetivo": correo_objetivo,
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
            accion="cambiar_contrasena",
            usuario_autenticado=usuario_autenticado,
            resultado="error",
            mensaje="Usuario no encontrado",
            detalles={"correo_objetivo": correo_objetivo}
        )
        return {
            "statusCode": 404,
            "headers": CORS_HEADERS,
            "body": json.dumps({"message": "Usuario no encontrado"})
        }

    usuario_objetivo = resp["Item"]

    if usuario_autenticado["rol"] != "autoridad" and correo_objetivo != usuario_autenticado["correo"]:
        _log_event(
            accion="cambiar_contrasena",
            usuario_autenticado=usuario_autenticado,
            resultado="error",
            mensaje="No tienes permiso para cambiar la contraseña de este usuario",
            detalles={
                "correo_objetivo": correo_objetivo,
                "rol_autenticado": usuario_autenticado["rol"]
            }
        )
        return {
            "statusCode": 403,
            "headers": CORS_HEADERS,
            "body": json.dumps({"message": "No tienes permiso para cambiar la contraseña de este usuario"})
        }

    if requiere_actual and usuario_objetivo.get("contrasena") != contrasena_actual:
        _log_event(
            accion="cambiar_contrasena",
            usuario_autenticado=usuario_autenticado,
            resultado="error",
            mensaje="La contraseña actual no coincide",
            detalles={"correo_objetivo": correo_objetivo}
        )
        return {
            "statusCode": 400,
            "headers": CORS_HEADERS,
            "body": json.dumps({"message": "La contraseña actual no coincide"})
        }

    try:
        usuarios_table.update_item(
            Key={"correo": correo_objetivo},
            UpdateExpression="SET contrasena = :nueva",
            ExpressionAttributeValues={":nueva": nueva_contrasena}
        )
    except Exception as e:
        _log_event(
            accion="cambiar_contrasena",
            usuario_autenticado=usuario_autenticado,
            resultado="error",
            mensaje="Error al actualizar contraseña",
            detalles={
                "correo_objetivo": correo_objetivo,
                "error": str(e)[:500]
            }
        )
        return {
            "statusCode": 500,
            "headers": CORS_HEADERS,
            "body": json.dumps({"message": f"Error al actualizar contraseña: {str(e)}"})
        }

    _log_event(
        accion="cambiar_contrasena",
        usuario_autenticado=usuario_autenticado,
        resultado="ok",
        mensaje="Contraseña actualizada correctamente",
        detalles={"correo_objetivo": correo_objetivo}
    )

    return {
        "statusCode": 200,
        "headers": CORS_HEADERS,
        "body": json.dumps({"message": "Contraseña actualizada correctamente"})
    }
