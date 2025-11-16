import json
import boto3
import os

TABLE_USUARIOS_NAME = os.getenv("TABLE_USUARIOS", "TABLE_USUARIOS")
CORS_HEADERS = {"Access-Control-Allow-Origin": "*"}

dynamodb = boto3.resource("dynamodb")
usuarios_table = dynamodb.Table(TABLE_USUARIOS_NAME)

def lambda_handler(event, context):
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

    query_params = event.get("queryStringParameters") or {}
    correo_solicitado = query_params.get("correo")
    if not correo_solicitado:
        return {
            "statusCode": 400,
            "body": json.dumps({"message": "correo es obligatorio"})
        }

    if usuario_autenticado["rol"] == "estudiante" and correo_solicitado != usuario_autenticado["correo"]:
        return {
            "statusCode": 403,
            "body": json.dumps({"message": "Solo puedes consultar tu propio perfil"})
        }

    try:
        resp = usuarios_table.get_item(Key={"correo": correo_solicitado})
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

    usuario = resp["Item"]
    rol_objetivo = usuario.get("rol", "estudiante")

    if (
        usuario_autenticado["rol"] == "personal_administrativo"
        and rol_objetivo == "autoridad"
        and correo_solicitado != usuario_autenticado["correo"]
    ):
        return {
            "statusCode": 403,
            "headers": CORS_HEADERS,
            "body": json.dumps({"message": "No puedes consultar el perfil de una autoridad"})
        }

    usuario.pop("contrasena", None)

    return {
        "statusCode": 200,
        "headers": CORS_HEADERS,
        "body": json.dumps({
            "message": "Usuario encontrado",
            "usuario": usuario
        })
    }
