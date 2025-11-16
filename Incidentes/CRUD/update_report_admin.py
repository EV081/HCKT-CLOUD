import os
import json
from datetime import datetime, timezone
import boto3
from CRUD.utils import validar_token
from botocore.exceptions import ClientError

dynamodb = boto3.resource('dynamodb')
table_name = os.environ.get('TABLE_INCIDENTES')
incidentes_table = dynamodb.Table(table_name)

ESTADO_ENUM = ["reportado", "en_progreso", "resuelto"]
ADMIN_ESTADOS_PERMITIDOS = ["en_progreso", "resuelto"]

def lambda_handler(event, context):
    headers = event.get("headers") or {}
    auth_header = headers.get("Authorization") or headers.get("authorization") or ""
    if auth_header.lower().startswith("bearer "):
        auth_header = auth_header.split(" ", 1)[1].strip()
    token = auth_header

    resultado_validacion = validar_token(token)
    
    if not resultado_validacion.get("valido"):
        return {
            "statusCode": 401,
            "body": json.dumps({"message": resultado_validacion.get("error")})
        }
    
    usuario_autenticado = {
        "correo": resultado_validacion.get("correo"),
        "rol": resultado_validacion.get("rol")
    }
    
    if usuario_autenticado["rol"] != "personal_administrativo":
        return {
            "statusCode": 403,
            "body": json.dumps({"message": "Solo un administrador puede cambiar el estado del incidente"})
        }

    body = json.loads(event.get('body', '{}'))
    
    incidente_id = body.get('incidente_id')
    if not incidente_id:
        return {
            "statusCode": 400,
            "body": json.dumps({"message": "Falta 'incidente_id' en el body"})
        }

    if "estado" not in body:
        return {
            "statusCode": 400,
            "body": json.dumps({"message": "Falta 'estado' en el body"})
        }

    estado_nuevo = body["estado"]

    if estado_nuevo not in ESTADO_ENUM or estado_nuevo not in ADMIN_ESTADOS_PERMITIDOS:
        return {
            "statusCode": 400,
            "body": json.dumps({"message": "El estado debe ser 'en_progreso' o 'resuelto' para Admin"})
        }

    try:
        response = incidentes_table.get_item(Key={'incidente_id': incidente_id})
        if 'Item' not in response:
            return {
                "statusCode": 404,
                "body": json.dumps({"message": "Incidente no encontrado"})
            }
        
        incidente_actual = response['Item']
    except ClientError as e:
        return {
            "statusCode": 500,
            "body": json.dumps({"message": f"Error al obtener el incidente: {str(e)}"})
        }

    incidente_actual["estado"] = estado_nuevo
    incidente_actual["updated_at"] = datetime.now(timezone.utc).isoformat()
    
    try:
        incidentes_table.put_item(Item=incidente_actual)
        return {
            "statusCode": 200,
            "body": json.dumps({
                "message": "Estado actualizado correctamente",
                "incidente_id": incidente_id,
                "nuevo_estado": estado_nuevo
            })
        }
    except ClientError as e:
        return {
            "statusCode": 500,
            "body": json.dumps({"message": f"Error al actualizar el incidente: {str(e)}"})
        }
