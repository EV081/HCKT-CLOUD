import boto3
import os
import json
from botocore.exceptions import ClientError
from CRUD.utils import ALLOWED_ROLES

TABLE_USUARIOS_NAME = os.getenv("TABLE_USUARIOS", "TABLE_USUARIOS")

dynamodb = boto3.resource("dynamodb")
usuarios_table = dynamodb.Table(TABLE_USUARIOS_NAME)

def _parse_body(event):
    body = event.get("body", {})
    if isinstance(body, str):
        body = json.loads(body) if body.strip() else {}
    elif not isinstance(body, dict):
        body = {}
    return body

def lambda_handler(event, context):
    body = _parse_body(event)
    authorizer = event.get("requestContext", {}).get("authorizer", {})
    usuario_autenticado = {
        "correo": authorizer.get("correo"),
        "rol": authorizer.get("rol"),
    }

    correo_objetivo = body.get("correo", usuario_autenticado["correo"])
    if not correo_objetivo:
        return {
            "statusCode": 400,
            "body": json.dumps({"message": "correo es obligatorio"})
        }

    try:
        resp = usuarios_table.get_item(Key={"correo": correo_objetivo})
    except Exception as e:
        return {
            "statusCode": 500,
            "body": json.dumps({"message": f"Error al obtener usuario: {str(e)}"})
        }

    if "Item" not in resp:
        return {
            "statusCode": 404,
            "body": json.dumps({"message": "Usuario no encontrado"})
        }

    usuario_actual = resp["Item"]
    rol_objetivo = usuario_actual.get("rol", "estudiante")
    rol_solicitante = usuario_autenticado["rol"]

    if rol_solicitante == "estudiante" and correo_objetivo != usuario_autenticado["correo"]:
        return {
            "statusCode": 403,
            "body": json.dumps({"message": "Solo puedes modificar tu propio perfil"})
        }

    if rol_solicitante == "personal_administrativo":
        if correo_objetivo != usuario_autenticado["correo"] and rol_objetivo != "estudiante":
            return {
                "statusCode": 403,
                "body": json.dumps({"message": "Solo puedes modificar estudiantes o tu propio perfil"})
            }

    if rol_objetivo == "autoridad" and rol_solicitante != "autoridad" and correo_objetivo != usuario_autenticado["correo"]:
        return {
            "statusCode": 403,
            "body": json.dumps({"message": "No puedes modificar una autoridad"})
        }

    if "rol" in body and rol_solicitante != "autoridad":
        return {
            "statusCode": 403,
            "body": json.dumps({"message": "No tienes permiso para cambiar el rol"})
        }

    usuario_modificado = usuario_actual.copy()
    hubo_cambios = False

    if "nombre" in body:
        usuario_modificado["nombre"] = body["nombre"]
        hubo_cambios = True

    if "contrasena" in body:
        if len(body["contrasena"]) < 6:
            return {
                "statusCode": 400,
                "body": json.dumps({"message": "La contraseña debe tener al menos 6 caracteres"})
            }
        usuario_modificado["contrasena"] = body["contrasena"]
        hubo_cambios = True

    if "rol" in body:
        nuevo_rol = body["rol"]
        if nuevo_rol not in ALLOWED_ROLES:
            return {
                "statusCode": 400,
                "body": json.dumps({"message": "Rol inválido"})
            }
        usuario_modificado["rol"] = nuevo_rol
        hubo_cambios = True

    nuevo_correo = body.get("nuevo_correo")
    if nuevo_correo and nuevo_correo != correo_objetivo:
        if "@" not in nuevo_correo:
            return {
                "statusCode": 400,
                "body": json.dumps({"message": "Correo electrónico inválido"})
            }
        try:
            existe_nuevo = usuarios_table.get_item(Key={"correo": nuevo_correo})
        except Exception as e:
            return {
                "statusCode": 500,
                "body": json.dumps({"message": f"Error al validar correo: {str(e)}"})
            }
        if "Item" in existe_nuevo:
            return {
                "statusCode": 400,
                "body": json.dumps({"message": "El nuevo correo ya está registrado"})
            }
        usuario_modificado["correo"] = nuevo_correo
        hubo_cambios = True

    if not hubo_cambios:
        return {
            "statusCode": 400,
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
            return {
                "statusCode": 400,
                "body": json.dumps({"message": "El nuevo correo ya está registrado"})
            }
        return {
            "statusCode": 500,
            "body": json.dumps({"message": f"Error al actualizar usuario: {str(e)}"})
        }
    except Exception as e:
        return {
            "statusCode": 500,
            "body": json.dumps({"message": f"Error al actualizar usuario: {str(e)}"})
        }

    usuario_modificado.pop("contrasena", None)

    return {
        "statusCode": 200,
        "body": json.dumps({
            "message": "Usuario actualizado correctamente",
            "usuario": usuario_modificado
        })
    }
