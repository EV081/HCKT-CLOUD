import json
import boto3
import os

TABLE_USUARIOS_NAME = os.getenv("TABLE_USUARIOS", "TABLE_USUARIOS")

dynamodb = boto3.resource("dynamodb")
usuarios_table = dynamodb.Table(TABLE_USUARIOS_NAME)

def lambda_handler(event, context):
    # Obtener usuario autenticado desde el authorizer
    authorizer = event.get("requestContext", {}).get("authorizer", {})
    usuario_autenticado = {
        "correo": authorizer.get("correo"),
        "role": authorizer.get("role")
    }

    # Obtener correo del query parameter
    correo_solicitado = event.get("queryStringParameters", {}).get("correo", usuario_autenticado["correo"])

    # Verificar permisos: un usuario solo puede ver su propia información
    if usuario_autenticado["correo"] != correo_solicitado and usuario_autenticado["role"] != "admin":
        return {
            "statusCode": 403,
            "body": json.dumps({"message": "Solo puedes ver tu propia información"})
        }

    # Obtener información del usuario
    try:
        resp = usuarios_table.get_item(Key={"correo": correo_solicitado})
        
        if "Item" not in resp:
            return {
                "statusCode": 404,
                "body": json.dumps({"message": "Usuario no encontrado"})
            }
        
        usuario = resp["Item"]
        
        # Eliminar la contraseña antes de devolver los datos
        if "contrasena" in usuario:
            del usuario["contrasena"]
        
        return {
            "statusCode": 200,
            "body": json.dumps({
                "message": "Usuario encontrado",
                "usuario": usuario
            })
        }
    except Exception as e:
        return {
            "statusCode": 500,
            "body": json.dumps({"message": f"Error al obtener usuario: {str(e)}"})
        }
