import json
import boto3
import os
import uuid
from datetime import datetime, timezone
from botocore.exceptions import ClientError
from CRUD.utils import generar_token, ALLOWED_ROLES

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
            if raw_body:
                try:
                    body = json.loads(raw_body)
                except json.JSONDecodeError:
                    body = {"__invalid_json__": raw_body}
            else:
                body = {}
        elif isinstance(raw_body, dict):
            body = raw_body
        else:
            body = {}
    elif isinstance(event, dict):
        body = event
    elif isinstance(event, str):
        try:
            body = json.loads(event)
        except json.JSONDecodeError:
            body = {"__invalid_json__": event}

    return body if isinstance(body, dict) else {}


def _log_event(accion, resultado, mensaje=None, detalles=None):
    """
    Registra un log en DynamoDB.
    IMPORTANTE: no guardar contraseñas ni tokens.
    """
    try:
        safe_detalles = None
        if detalles:
            safe_detalles = dict(detalles)
            if "contrasena" in safe_detalles:
                safe_detalles["contrasena"] = "***"
            if "password" in safe_detalles:
                safe_detalles["password"] = "***"
            if "token" in safe_detalles:
                safe_detalles["token"] = "***"

        item = {
            "id": str(uuid.uuid4()),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "servicio": "usuarios-login",
            "accion": accion,
            "resultado": resultado,
        }

        if mensaje:
            item["mensaje"] = mensaje

        if safe_detalles:
            item["detalles"] = safe_detalles

        logs_table.put_item(Item=item)
    except Exception:
        pass


def lambda_handler(event, context):
    body = _parse_body(event)

    if "__invalid_json__" in body:
        raw_body = body.get("__invalid_json__")
        _log_event(
            accion="login",
            resultado="error",
            mensaje="Body JSON inválido",
            detalles={"body_raw_len": len(raw_body) if raw_body else 0}
        )
        return {
            "statusCode": 400,
            "headers": CORS_HEADERS,
            "body": json.dumps({"message": "Body JSON inválido"})
        }

    correo = body.get("correo")
    contrasena = body.get("contrasena")

    if not correo or not contrasena:
        _log_event(
            accion="login",
            resultado="error",
            mensaje="correo y contrasena son obligatorios",
            detalles={"correo": correo or None}
        )
        return {
            "statusCode": 400,
            "headers": CORS_HEADERS,
            "body": json.dumps({"message": "correo y contrasena son obligatorios"})
        }

    try:
        resp = usuarios_table.get_item(Key={"correo": correo})
    except ClientError as e:
        _log_event(
            accion="login",
            resultado="error",
            mensaje="Error al obtener usuario de DynamoDB",
            detalles={"correo": correo, "error": str(e)[:500]}
        )
        return {
            "statusCode": 500,
            "headers": CORS_HEADERS,
            "body": json.dumps({"message": "Error al obtener usuario"})
        }

    if "Item" not in resp:
        _log_event(
            accion="login",
            resultado="error",
            mensaje="Credenciales inválidas (usuario no encontrado)",
            detalles={"correo": correo}
        )
        return {
            "statusCode": 401,
            "headers": CORS_HEADERS,
            "body": json.dumps({"message": "Credenciales inválidas"})
        }

    usuario = resp["Item"]
    rol_usuario = usuario.get("rol")

    if rol_usuario not in ALLOWED_ROLES:
        _log_event(
            accion="login",
            resultado="error",
            mensaje="Rol de usuario inválido",
            detalles={"correo": correo, "rol_usuario": rol_usuario}
        )
        return {
            "statusCode": 500,
            "headers": CORS_HEADERS,
            "body": json.dumps({"message": "Rol de usuario inválido"})
        }

    if usuario.get("contrasena") != contrasena:
        _log_event(
            accion="login",
            resultado="error",
            mensaje="Credenciales inválidas (password incorrecto)",
            detalles={"correo": correo}
        )
        return {
            "statusCode": 401,
            "headers": CORS_HEADERS,
            "body": json.dumps({"message": "Credenciales inválidas"})
        }
    
    try:
        token = generar_token(
            correo=usuario["correo"],
            role=rol_usuario,
            nombre=usuario.get("nombre", "")
        )
    except Exception as e:
        _log_event(
            accion="login",
            resultado="error",
            mensaje="Error al generar token",
            detalles={"correo": correo, "error": str(e)[:500]}
        )
        return {
            "statusCode": 500,
            "headers": CORS_HEADERS,
            "body": json.dumps({"message": "Error al generar token"})
        }

    _log_event(
        accion="login",
        resultado="ok",
        mensaje="Login exitoso",
        detalles={"correo": correo, "rol_usuario": rol_usuario}
    )

    return {
        "statusCode": 200,
        "headers": CORS_HEADERS,
        "body": json.dumps({
            "message": "Login exitoso",
            "token": token,
            "usuario": {
                "correo": usuario["correo"],
                "nombre": usuario.get("nombre", ""),
                "rol": rol_usuario
            }
        })
    }
