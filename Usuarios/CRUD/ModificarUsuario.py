import boto3
import os
import json
import uuid
from datetime import datetime, timezone
from botocore.exceptions import ClientError
from CRUD.utils import ALLOWED_ROLES

TABLE_USUARIOS_NAME = os.getenv("TABLE_USUARIOS", "TABLE_USUARIOS")
TABLE_LOGS_NAME = os.getenv("TABLE_LOGS", "TABLE_LOGS")
CORS_HEADERS = {"Access-Control-Allow-Origin": "*"}

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
    IMPORTANTE: no guardar contraseñas.
    """
    try:
        safe_detalles = None
        if detalles:
            safe_detalles = dict(detalles)
            if "contrasena" in safe_detalles:
                safe_detalles["contrasena"] = "***"
            if "nueva_contrasena" in safe_detalles:
                safe_detalles["nueva_contrasena"] = "***"

        item = {
            "id": str(uuid.uuid4()),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "servicio": "usuarios-actualizar",
            "accion": accion,
            "resultado": resultado,
        }

        if usuario_autenticado:
            item["usuario"] = usuario_autenticado.get("correo")
            item["rol"] = usuario_autenticado.get("rol")

        if mensaje:
            item["mensaje"] = mensaje

        if safe_detalles:
            item["detalles"] = safe_detalles

        logs_table.put_item(Item=item)
    except Exception:
        pass


def lambda_handler(event, context):
    body = _parse_body(event)
    authorizer = event.get("requestContext", {}).get("authorizer", {})

    if not authorizer:
        _log_event(
            accion="actualizar_usuario",
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
        "rol": authorizer.get("rol"),
    }

    correo_objetivo = body.get("correo", usuario_autenticado["correo"])
    if not correo_objetivo:
        _log_event(
            accion="actualizar_usuario",
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
        resp = usuarios_table.get_item(Key={"correo": correo_objetivo})
    except Exception as e:
        _log_event(
            accion="actualizar_usuario",
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
            accion="actualizar_usuario",
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

    usuario_actual = resp["Item"]
    rol_objetivo = usuario_actual.get("rol", "estudiante")
    rol_solicitante = usuario_autenticado["rol"]

    if rol_solicitante == "estudiante" and correo_objetivo != usuario_autenticado["correo"]:
        _log_event(
            accion="actualizar_usuario",
            usuario_autenticado=usuario_autenticado,
            resultado="error",
            mensaje="Solo puedes modificar tu propio perfil",
            detalles={
                "correo_objetivo": correo_objetivo,
                "rol_objetivo": rol_objetivo
            }
        )
        return {
            "statusCode": 403,
            "headers": CORS_HEADERS,
            "body": json.dumps({"message": "Solo puedes modificar tu propio perfil"})
        }

    if rol_solicitante == "personal_administrativo":
        if correo_objetivo != usuario_autenticado["correo"] and rol_objetivo != "estudiante":
            _log_event(
                accion="actualizar_usuario",
                usuario_autenticado=usuario_autenticado,
                resultado="error",
                mensaje="Solo puedes modificar estudiantes o tu propio perfil",
                detalles={
                    "correo_objetivo": correo_objetivo,
                    "rol_objetivo": rol_objetivo
                }
            )
            return {
                "statusCode": 403,
                "headers": CORS_HEADERS,
                "body": json.dumps({"message": "Solo puedes modificar estudiantes o tu propio perfil"})
            }

    if rol_objetivo == "autoridad" and rol_solicitante != "autoridad" and correo_objetivo != usuario_autenticado["correo"]:
        _log_event(
            accion="actualizar_usuario",
            usuario_autenticado=usuario_autenticado,
            resultado="error",
            mensaje="No puedes modificar una autoridad",
            detalles={
                "correo_objetivo": correo_objetivo,
                "rol_objetivo": rol_objetivo,
                "rol_solicitante": rol_solicitante
            }
        )
        return {
            "statusCode": 403,
            "headers": CORS_HEADERS,
            "body": json.dumps({"message": "No puedes modificar una autoridad"})
        }

    if "rol" in body and rol_solicitante != "autoridad":
        _log_event(
            accion="actualizar_usuario",
            usuario_autenticado=usuario_autenticado,
            resultado="error",
            mensaje="No tienes permiso para cambiar el rol",
            detalles={
                "correo_objetivo": correo_objetivo,
                "rol_solicitante": rol_solicitante
            }
        )
        return {
            "statusCode": 403,
            "headers": CORS_HEADERS,
            "body": json.dumps({"message": "No tienes permiso para cambiar el rol"})
        }

    usuario_modificado = usuario_actual.copy()
    hubo_cambios = False
    campos_cambiados = []

    if "nombre" in body:
        usuario_modificado["nombre"] = body["nombre"]
        hubo_cambios = True
        campos_cambiados.append("nombre")

    if "contrasena" in body:
        if len(body["contrasena"]) < 6:
            _log_event(
                accion="actualizar_usuario",
                usuario_autenticado=usuario_autenticado,
                resultado="error",
                mensaje="La contraseña debe tener al menos 6 caracteres",
                detalles={"correo_objetivo": correo_objetivo}
            )
            return {
                "statusCode": 400,
                "headers": CORS_HEADERS,
                "body": json.dumps({"message": "La contraseña debe tener al menos 6 caracteres"})
            }
        usuario_modificado["contrasena"] = body["contrasena"]
        hubo_cambios = True
        campos_cambiados.append("contrasena")

    if "rol" in body:
        nuevo_rol = body["rol"]
        if nuevo_rol not in ALLOWED_ROLES:
            _log_event(
                accion="actualizar_usuario",
                usuario_autenticado=usuario_autenticado,
                resultado="error",
                mensaje="Rol inválido",
                detalles={
                    "correo_objetivo": correo_objetivo,
                    "nuevo_rol": nuevo_rol
                }
            )
            return {
                "statusCode": 400,
                "headers": CORS_HEADERS,
                "body": json.dumps({"message": "Rol inválido"})
            }
        usuario_modificado["rol"] = nuevo_rol
        hubo_cambios = True
        campos_cambiados.append("rol")

    nuevo_correo = body.get("nuevo_correo")
    if nuevo_correo and nuevo_correo != correo_objetivo:
        if "@" not in nuevo_correo:
            _log_event(
                accion="actualizar_usuario",
                usuario_autenticado=usuario_autenticado,
                resultado="error",
                mensaje="Correo electrónico inválido",
                detalles={
                    "correo_objetivo": correo_objetivo,
                    "nuevo_correo": nuevo_correo
                }
            )
            return {
                "statusCode": 400,
                "headers": CORS_HEADERS,
                "body": json.dumps({"message": "Correo electrónico inválido"})
            }
        try:
            existe_nuevo = usuarios_table.get_item(Key={"correo": nuevo_correo})
        except Exception as e:
            _log_event(
                accion="actualizar_usuario",
                usuario_autenticado=usuario_autenticado,
                resultado="error",
                mensaje="Error al validar nuevo correo",
                detalles={
                    "correo_objetivo": correo_objetivo,
                    "nuevo_correo": nuevo_correo,
                    "error": str(e)[:500]
                }
            )
            return {
                "statusCode": 500,
                "headers": CORS_HEADERS,
                "body": json.dumps({"message": f"Error al validar correo: {str(e)}"})
            }
        if "Item" in existe_nuevo:
            _log_event(
                accion="actualizar_usuario",
                usuario_autenticado=usuario_autenticado,
                resultado="error",
                mensaje="El nuevo correo ya está registrado",
                detalles={
                    "correo_objetivo": correo_objetivo,
                    "nuevo_correo": nuevo_correo
                }
            )
            return {
                "statusCode": 400,
                "headers": CORS_HEADERS,
                "body": json.dumps({"message": "El nuevo correo ya está registrado"})
            }
        usuario_modificado["correo"] = nuevo_correo
        hubo_cambios = True
        campos_cambiados.append("nuevo_correo")

    if not hubo_cambios:
        _log_event(
            accion="actualizar_usuario",
            usuario_autenticado=usuario_autenticado,
            resultado="error",
            mensaje="No hay campos para actualizar",
            detalles={"correo_objetivo": correo_objetivo}
        )
        return {
            "statusCode": 400,
            "headers": CORS_HEADERS,
            "body": json.dumps({"message": "No hay campos para actualizar"})
        }

    try:
        if nuevo_correo and nuevo_correo != correo_objetivo:
            usuarios_table.put_item(
                Item=usuario_modificado,
                ConditionExpression="attribute_not_exists(correo)"
            )
            usuarios_table.delete_item(Key={"correo": correo_objetivo})
            correo_objetivo = nuevo_correo
        else:
            usuarios_table.put_item(Item=usuario_modificado)
    except ClientError as e:
        if e.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
            _log_event(
                accion="actualizar_usuario",
                usuario_autenticado=usuario_autenticado,
                resultado="error",
                mensaje="El nuevo correo ya está registrado (condición fallida)",
                detalles={
                    "correo_objetivo": correo_objetivo,
                    "nuevo_correo": nuevo_correo
                }
            )
            return {
                "statusCode": 400,
                "headers": CORS_HEADERS,
                "body": json.dumps({"message": "El nuevo correo ya está registrado"})
            }
        _log_event(
            accion="actualizar_usuario",
            usuario_autenticado=usuario_autenticado,
            resultado="error",
            mensaje="Error al actualizar usuario (ClientError)",
            detalles={
                "correo_objetivo": correo_objetivo,
                "nuevo_correo": nuevo_correo,
                "error": str(e)[:500]
            }
        )
        return {
            "statusCode": 500,
            "headers": CORS_HEADERS,
            "body": json.dumps({"message": f"Error al actualizar usuario: {str(e)}"})
        }
    except Exception as e:
        _log_event(
            accion="actualizar_usuario",
            usuario_autenticado=usuario_autenticado,
            resultado="error",
            mensaje="Error al actualizar usuario",
            detalles={
                "correo_objetivo": correo_objetivo,
                "nuevo_correo": nuevo_correo,
                "error": str(e)[:500]
            }
        )
        return {
            "statusCode": 500,
            "headers": CORS_HEADERS,
            "body": json.dumps({"message": f"Error al actualizar usuario: {str(e)}"})
        }

    usuario_modificado.pop("contrasena", None)

    _log_event(
        accion="actualizar_usuario",
        usuario_autenticado=usuario_autenticado,
        resultado="ok",
        mensaje="Usuario actualizado correctamente",
        detalles={
            "correo_final": usuario_modificado.get("correo"),
            "campos_cambiados": campos_cambiados,
            "rol_antes": rol_objetivo,
            "rol_despues": usuario_modificado.get("rol", rol_objetivo)
        }
    )

    return {
        "statusCode": 200,
        "headers": CORS_HEADERS,
        "body": json.dumps({
            "message": "Usuario actualizado correctamente",
            "usuario": usuario_modificado
        })
    }
