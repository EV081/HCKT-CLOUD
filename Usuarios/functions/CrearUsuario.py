import json
import boto3
import os
import uuid
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

    # Extraer los campos del cuerpo
    nombre = body.get("nombre")
    correo = body.get("correo")
    contrasena = body.get("contrasena")
    rol = body.get("rol", "estudiante")  # Asignar valor por defecto si no se pasa

    # Validación de los campos obligatorios
    if not nombre or not correo or not contrasena or not rol:
        return {
            "statusCode": 400,
            "body": json.dumps({"message": "nombre, correo, contrasena y rol son obligatorios"})
        }

    # Validar formato de correo electrónico
    if "@" not in correo:
        return {
            "statusCode": 400,
            "body": json.dumps({"message": "Correo electrónico inválido"})
        }

    # Validar longitud mínima de la contraseña
    if len(contrasena) < 6:
        return {
            "statusCode": 400,
            "body": json.dumps({"message": "La contraseña debe tener al menos 6 caracteres"})
        }

    # Validar que el rol esté entre los valores permitidos
    if rol not in ["estudiante", "personal_administrativo", "autoridad"]:
        return {
            "statusCode": 400,
            "body": json.dumps({"message": "Rol inválido, debe ser 'estudiante', 'personal_administrativo' o 'autoridad'"})
        }

    # Validar si el usuario ya existe
    resp = usuarios_table.get_item(Key={"correo": correo})
    if "Item" in resp:
        return {
            "statusCode": 409,
            "body": json.dumps({"message": "El usuario ya existe"})
        }

    # Generar un ID único para el usuario
    usuario_id = str(uuid.uuid4())  # Generar un UUID para el usuario

    # Crear el item a insertar en DynamoDB
    item = {
        "usuario_id": usuario_id,
        "nombre": nombre,
        "correo": correo,
        "contrasena": contrasena,
        "rol": rol
    }

    # Insertar el nuevo usuario en la tabla
    usuarios_table.put_item(Item=item)

    # Generar token automáticamente al crear el usuario
    token = generar_token(
        correo=correo,
        role=rol,
        nombre=nombre
    )

    return {
        "statusCode": 201,
        "body": json.dumps({
            "message": "Usuario creado correctamente",
            "token": token,
            "usuario": {
                "usuario_id": usuario_id,
                "correo": correo,
                "nombre": nombre,
                "rol": rol
            }
        })
    }
