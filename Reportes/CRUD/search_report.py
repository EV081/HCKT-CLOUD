import os
import json
import boto3
from reportes.utils import validar_token
from botocore.exceptions import ClientError

dynamodb = boto3.resource('dynamodb')
table_name = os.environ.get('TABLE_INCIDENTES')
incidentes_table = dynamodb.Table(table_name)

def lambda_handler(event, context):
    token = event.get("headers", {}).get("authorization", "").split(" ")[-1]
    
    resultado_validacion = validar_token(token)
    
    if not resultado_validacion.get("valido"):
        return {
            "statusCode": 401,
            "body": json.dumps({"message": resultado_validacion.get("error")})
        }
    
    usuario_autenticado = {
        "correo": resultado_validacion.get("correo"),
        "role": resultado_validacion.get("role")
    }

    body = json.loads(event.get('body', '{}'))
    incidente_id = body.get('incidente_id')
    
    if not incidente_id:
        return {
            "statusCode": 400,
            "body": json.dumps({"message": "Falta 'incidente_id' en la solicitud"})
        }

    if usuario_autenticado["role"] == "admin":
        print("Acceso concedido como admin")
    elif usuario_autenticado["role"] == "operador":
        print("Acceso concedido como operador")
    elif usuario_autenticado["role"] == "user":
        print("Acceso concedido como user")
        if not incidente_id:
            return {
                "statusCode": 403,
                "body": json.dumps({"message": "Acceso denegado: Solo puedes ver tu propio reporte"})
            }

    try:
        response = incidentes_table.get_item(Key={'incidente_id': incidente_id})
        if 'Item' not in response:
            return {
                "statusCode": 404,
                "body": json.dumps({"message": "Incidente no encontrado"})
            }
        incidente = response['Item']
        
        if usuario_autenticado["role"] == "admin" and incidente.get('usuario_correo') != usuario_autenticado["correo"]:
            return {
                "statusCode": 403,
                "body": json.dumps({"message": "Acceso denegado: No puedes ver reportes de otros usuarios"})
            }

        if usuario_autenticado["role"] == "user" and incidente.get('usuario_correo') != usuario_autenticado["correo"]:
            return {
                "statusCode": 403,
                "body": json.dumps({"message": "Acceso denegado: Solo puedes ver tu propio reporte"})
            }
        
        return {
            "statusCode": 200,
            "body": json.dumps({
                "message": "Incidente encontrado",
                "incidente": incidente
            })
        }
    
    except ClientError as e:
        return {
            "statusCode": 500,
            "body": json.dumps({"message": f"Error al obtener el incidente: {str(e)}"})
        }
