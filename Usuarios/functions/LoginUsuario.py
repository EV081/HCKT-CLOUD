import json
import boto3
import os
from Usuarios.functions.utils import generar_token

TABLE_USUARIOS_NAME = os.getenv("TABLE_USUARIOS", "TABLE_USUARIOS")

dynamodb = boto3.resource("dynamodb")
usuarios_table = dynamodb.Table(TABLE_USUARIOS_NAME)

def lambda_handler(event, context):
    body = {}

    # Parseo del cuerpo del evento (si es JSON o dict)
    if isinstance(event, dict) and "body" in event:
        raw_body = event.get("body")
        if isinstance(raw_body, str):
            if raw_body:
                body = json.loads(raw_body)
            else:
                body = {}
        elif isinstance(raw_body, dict):
            body = raw_body
        else:
            body = {}
    elif isinstance(event, dict):
        body = event
    elif isinstance(event, str):
        body = json.loads(event)

    correo = body.get("correo")
    contrasena = body.get("contrasena")

    # Validación de los campos obligatorios
    if not correo or not contrasena:
        return {
            "statusCode": 400,
            "body": json.dumps({"message": "correo y contrasena son obligatorios"})
        }

    # Verificar si el usuario existe en DynamoDB
    resp = usuarios_table.get_item(Key={"correo": correo})
    if "Item" not in resp:
        return {
            "statusCode": 401,
            "body": json.dumps({"message": "Credenciales inválidas"})
        }

    usuario = resp["Item"]

    # Verificar si la contraseña es correcta
    if usuario.get("contrasena") != contrasena:
        return {
            "statusCode": 401,
            "body": json.dumps({"message": "Credenciales inválidas"})
        }

    # Generar el token JWT para el usuario autenticado
    token = generar_token(
        correo=usuario["correo"],
        role=usuario.get("rol", "estudiante"),
        nombre=usuario.get("nombre", "")
    )

    return {
        "statusCode": 200,
        "body": json.dumps({
            "message": "Login exitoso",
            "token": token,
            "usuario": {
                "correo": usuario["correo"],
                "nombre": usuario["nombre"],
                "rol": usuario.get("rol", "estudiante")
            }
        })
    }
