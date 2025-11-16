import json
import boto3
import os
from CRUD.utils import generar_token, validar_token, ALLOWED_ROLES

TABLE_USUARIOS_NAME = os.getenv("TABLE_USUARIOS", "TABLE_USUARIOS")

dynamodb = boto3.resource("dynamodb")
usuarios_table = dynamodb.Table(TABLE_USUARIOS_NAME)

def lambda_handler(event, context):
    body = {}
    headers = event.get("headers") or {}
    auth_header = headers.get("authorization") or headers.get("Authorization")
    rol_autenticado = None

    if auth_header:
        token = auth_header.split(" ")[-1]
        resultado_token = validar_token(token)
        if not resultado_token.get("valido"):
            return {
                "statusCode": 401,
                "body": json.dumps({"message": resultado_token.get("error", "Token inválido")})
            }
        rol_autenticado = resultado_token.get("rol")

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

    nombre = body.get("nombre")
    correo = body.get("correo")
    contrasena = body.get("contrasena")
    rol = body.get("rol", "estudiante")

    if not nombre or not correo or not contrasena or not rol:
        return {
            "statusCode": 400,
            "body": json.dumps({"message": "nombre, correo, contrasena y rol son obligatorios"})
        }

    if "@" not in correo:
        return {
            "statusCode": 400,
            "body": json.dumps({"message": "Correo electrónico inválido"})
        }

    if len(contrasena) < 6:
        return {
            "statusCode": 400,
            "body": json.dumps({"message": "La contraseña debe tener al menos 6 caracteres"})
        }

    if rol not in ALLOWED_ROLES:
        return {
            "statusCode": 400,
            "body": json.dumps({"message": "Rol inválido, debe ser 'estudiante', 'personal_administrativo' o 'autoridad'"})
        }

    if not rol_autenticado:
        if rol != "estudiante":
            return {
                "statusCode": 403,
                "body": json.dumps({"message": "Solo puedes auto-registrarte como estudiante"})
            }
    elif rol_autenticado != "autoridad":
        return {
            "statusCode": 403,
            "body": json.dumps({"message": "Solo una autoridad puede crear usuarios adicionales"})
        }

    resp = usuarios_table.get_item(Key={"correo": correo})
    if "Item" in resp:
        return {
            "statusCode": 400,
            "body": json.dumps({"error": "El correo ya está registrado"})
        }

    item = {
        "nombre": nombre,
        "correo": correo,
        "contrasena": contrasena,
        "rol": rol
    }

    usuarios_table.put_item(Item=item)

    respuesta = {
        "message": "Usuario creado correctamente",
        "usuario": {
            "correo": correo,
            "nombre": nombre,
            "rol": rol
        }
    }

    if not rol_autenticado:
        respuesta["token"] = generar_token(correo=correo, role=rol, nombre=nombre)

    return {
        "statusCode": 201,
        "body": json.dumps(respuesta)
    }
