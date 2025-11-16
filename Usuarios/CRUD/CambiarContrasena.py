import json
import boto3
import os

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
    if not authorizer:
        return {
            "statusCode": 401,
            "body": json.dumps({"message": "Token requerido"})
        }

    usuario_autenticado = {
        "correo": authorizer.get("correo"),
        "rol": authorizer.get("rol")
    }

    correo_objetivo = body.get("correo", usuario_autenticado["correo"])
    if not correo_objetivo:
        return {
            "statusCode": 400,
            "body": json.dumps({"message": "correo es obligatorio"})
        }

    nueva_contrasena = body.get("nueva_contrasena")
    if not nueva_contrasena or len(nueva_contrasena) < 6:
        return {
            "statusCode": 400,
            "body": json.dumps({"message": "La nueva contraseña debe tener al menos 6 caracteres"})
        }

    requiere_actual = True
    if usuario_autenticado["rol"] == "autoridad" and correo_objetivo != usuario_autenticado["correo"]:
        requiere_actual = False

    contrasena_actual = body.get("contrasena_actual") if requiere_actual else None

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

    usuario_objetivo = resp["Item"]

    if usuario_autenticado["rol"] != "autoridad" and correo_objetivo != usuario_autenticado["correo"]:
        return {
            "statusCode": 403,
            "body": json.dumps({"message": "No tienes permiso para cambiar la contraseña de este usuario"})
        }

    if requiere_actual and usuario_objetivo.get("contrasena") != contrasena_actual:
        return {
            "statusCode": 400,
            "body": json.dumps({"message": "La contraseña actual no coincide"})
        }

    try:
        usuarios_table.update_item(
            Key={"correo": correo_objetivo},
            UpdateExpression="SET contrasena = :nueva",
            ExpressionAttributeValues={":nueva": nueva_contrasena}
        )
    except Exception as e:
        return {
            "statusCode": 500,
            "body": json.dumps({"message": f"Error al actualizar contraseña: {str(e)}"})
        }

    return {
        "statusCode": 200,
        "body": json.dumps({"message": "Contraseña actualizada correctamente"})
    }
