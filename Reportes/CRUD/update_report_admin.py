import os
import json
from datetime import datetime
import boto3
from reportes.utils import validar_token
from botocore.exceptions import ClientError

dynamodb = boto3.resource('dynamodb')
table_name = os.environ.get('TABLE_INCIDENTES')
incidentes_table = dynamodb.Table(table_name)

ESTADO_ENUM = ["reportado", "en_progreso", "resuelto"]

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
    
    incidente_id = event.get('pathParameters', {}).get('incidente_id')
    if not incidente_id:
        return {
            "statusCode": 400,
            "body": json.dumps({"message": "Falta 'incidente_id' en la solicitud"})
        }
    
    body = json.loads(event.get('body', '{}'))
    

    if usuario_autenticado["role"] == "Admin":
        if "estado" not in body or body["estado"] not in ESTADO_ENUM:
            return {
                "statusCode": 400,
                "body": json.dumps({"message": "El estado debe ser 'en_progreso' o 'resuelto' para Admin"})
            }
        
        estado_nuevo = body["estado"]

        try:
            response = incidentes_table.get_item(Key={'incidente_id': incidente_id})
            if 'Item' not in response:
                return {
                    "statusCode": 404,
                    "body": json.dumps({"message": "Incidente no encontrado"})
                }
            
            incidente_actual = response['Item']
            
            incidente_actual["estado"] = estado_nuevo
            incidente_actual["updated_at"] = datetime.utcnow().isoformat()
            
            incidentes_table.put_item(Item=incidente_actual)

            return {
                "statusCode": 200,
                "body": json.dumps({
                    "message": "Estado actualizado correctamente",
                    "incidente_id": incidente_id
                })
            }
        
        except ClientError as e:
            return {
                "statusCode": 500,
                "body": json.dumps({"message": f"Error al actualizar el incidente: {str(e)}"})
            }
    
    else:
        return {
            "statusCode": 403,
            "body": json.dumps({"message": "Solo un administrador puede cambiar el estado del incidente"})
        }
