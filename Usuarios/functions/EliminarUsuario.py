import json
import boto3
import os
from Usuarios.functions.utils import verificar_rol

TABLE_USUARIOS_NAME = os.getenv("TABLE_USUARIOS", "TABLE_USUARIOS")

dynamodb = boto3.resource("dynamodb")
usuarios_table = dynamodb.Table(TABLE_USUARIOS_NAME)

def lambda_handler(event, context):
    # Obtener usuario autenticado desde el contexto del evento
    authorizer = event.get("requestContext", {}).get("authorizer", {})
    usuario_autenticado = {
        "correo": authorizer.get("correo"),
        "role": authorizer.get("role")
    }
    
    # Procesar el cuerpo del evento
    body = {}
    if isinstance(event, dict) and "body" in event:
        raw_body = event.get("body")
        if isinstance(raw_body, str):
            if raw_body:
                body = json.loads(raw_body)
            else:
                body = {}
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
    resp = usuarios_table.get_item(Key={"correo": correo_a_eliminar})
    if "Item" not in resp:
        return {
            "statusCode": 404,
            "body": json.dumps({"message": "Usuario no encontrado"})
        }
    
    usuario_a_eliminar = resp["Item"]
    usuario_id_a_eliminar = usuario_a_eliminar.get("usuario_id")
    rol_a_eliminar = usuario_a_eliminar.get("rol", "estudiante")

    # Lógica de permisos: verificar si el usuario autenticado puede eliminar al usuario
    # Se pueden eliminar usuarios solo si son el mismo usuario o si tienen rol 'autoridad'
    es_mismo_usuario = usuario_autenticado["correo"] == correo_a_eliminar
    es_autoridad = verificar_rol(usuario_autenticado, ["autoridad"])
    
    # Si es el mismo usuario o tiene el rol de autoridad, se puede eliminar
    if es_mismo_usuario or es_autoridad:
        usuarios_table.delete_item(Key={"correo": correo_a_eliminar})
        return {
            "statusCode": 200,
            "body": json.dumps({"message": "Usuario eliminado correctamente"})
        }
    
    # Si no tiene permisos suficientes
    return {
        "statusCode": 403,
        "body": json.dumps({"message": "No tienes permiso para eliminar este usuario"})
    }
