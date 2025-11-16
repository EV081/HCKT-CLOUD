import os
import json
import boto3
from decimal import Decimal
from CRUD.utils import validar_token
from botocore.exceptions import ClientError

dynamodb = boto3.resource('dynamodb')
table_name = os.environ.get('TABLE_INCIDENTES')
incidentes_table = dynamodb.Table(table_name)

def _convert_decimals(obj):
    """
    Convierte recursivamente Decimal -> int/float para que sea JSON serializable.
    """
    if isinstance(obj, list):
        return [_convert_decimals(x) for x in obj]
    if isinstance(obj, dict):
        return {k: _convert_decimals(v) for k, v in obj.items()}
    if isinstance(obj, Decimal):
        if obj % 1 == 0:
            return int(obj)
        return float(obj)
    return obj

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

    body = json.loads(event.get('body', '{}'))
    incidente_id = body.get('incidente_id')
    
    if not incidente_id:
        return {
            "statusCode": 400,
            "body": json.dumps({"message": "Falta 'incidente_id' en la solicitud"})
        }

    try:
        response = incidentes_table.get_item(Key={'incidente_id': incidente_id})
        if 'Item' not in response:
            return {
                "statusCode": 404,
                "body": json.dumps({"message": "Incidente no encontrado"})
            }
        incidente = response['Item']
    except ClientError as e:
        return {
            "statusCode": 500,
            "body": json.dumps({"message": f"Error al obtener el incidente: {str(e)}"})
        }

    rol = usuario_autenticado["rol"]
    correo_usuario = usuario_autenticado["correo"]
    correo_propietario = incidente.get('usuario_correo')


    if rol in ["personal_administrativo", "autoridad"]:
        pass
    elif rol == "estudiante":
        if correo_propietario != correo_usuario:
            return {
                "statusCode": 403,
                "body": json.dumps({"message": "Acceso denegado: Solo puedes ver tu propio reporte"})
            }
    else:
        return {
            "statusCode": 403,
            "body": json.dumps({"message": "No tienes permisos para ver incidentes"})
        }

    incidente_sin_decimals = _convert_decimals(incidente)
    
    return {
        "statusCode": 200,
        "body": json.dumps({
            "message": "Incidente encontrado",
            "incidente": incidente_sin_decimals
        })
    }
