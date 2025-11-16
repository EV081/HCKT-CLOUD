import json
import boto3
import os

TABLE_USUARIOS_NAME = os.getenv("TABLE_USUARIOS", "TABLE_USUARIOS")

dynamodb = boto3.resource("dynamodb")
usuarios_table = dynamodb.Table(TABLE_USUARIOS_NAME)

def lambda_handler(event, context):
    # Obtener usuario autenticado desde el contexto del evento
    authorizer = event.get("requestContext", {}).get("authorizer", {})
    usuario_autenticado = {
        "correo": authorizer.get("correo"),
        "rol": authorizer.get("rol")
    }
    
    # Procesar el cuerpo del evento
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

    correo_a_eliminar = body.get("correo")
    if not correo_a_eliminar:
        return {
            "statusCode": 400,
            "body": json.dumps({"message": "correo es obligatorio"})
        }

    # Obtener información del usuario a eliminar
    try:
        resp = usuarios_table.get_item(Key={"correo": correo_a_eliminar})
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
    
    usuario_a_eliminar = resp["Item"]
    rol_a_eliminar = usuario_a_eliminar.get("rol", "estudiante")

    # Lógica de permisos: verificar si el usuario autenticado puede eliminar al usuario
    es_mismo_usuario = usuario_autenticado["correo"] == correo_a_eliminar
    rol_solicitante = usuario_autenticado["rol"]

    # Si es el mismo usuario, se permite la eliminación
    if es_mismo_usuario:
        pass
    # Si el rol del solicitante es 'autoridad', se permite la eliminación
    elif rol_solicitante == "autoridad":
        pass
    # Si el rol del solicitante es 'personal_administrativo', se restringe la eliminación a estudiantes o a su propia cuenta
    elif rol_solicitante == "personal_administrativo":
        if rol_a_eliminar != "estudiante":
            return {
                "statusCode": 403,
                "body": json.dumps({"message": "Solo puedes eliminar estudiantes o tu propia cuenta"})
            }
    # Si no tiene permisos suficientes
    else:
        return {
            "statusCode": 403,
            "body": json.dumps({"message": "No tienes permiso para eliminar este usuario"})
        }

    # Eliminar el usuario
    usuarios_table.delete_item(Key={"correo": correo_a_eliminar})
    return {
        "statusCode": 200,
        "body": json.dumps({"message": "Usuario eliminado correctamente"})
    }
