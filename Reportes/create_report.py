import os
import json
import uuid
import base64
import boto3
from datetime import datetime
from reportes.utils import validar_token
from botocore.exceptions import ClientError

dynamodb = boto3.resource('dynamodb')
s3 = boto3.client('s3')
table_name = os.environ.get('TABLE_INCIDENTES')
incidentes_table = dynamodb.Table(table_name)
INCIDENTES_BUCKET = os.environ.get('INCIDENTES_BUCKET')

TIPO_ENUM = ["limpieza", "TI" ,"seguridad", "mantenimiento", "otro"]
NIVEL_URGENCIA_ENUM = ["bajo", "medio", "alto", "critico"]
ESTADO_ENUM = ["reportado", "en_progreso", "resuelto"]
PISO_RANGO = range(-2, 12)

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
    
    if usuario_autenticado["role"] not in ["user", "admin"]:
        return {
            "statusCode": 403,
            "body": json.dumps({"message": "No tienes permisos para crear un incidente"})
        }
    
    body = json.loads(event.get('body', '{}'))
    
    required_fields = [
        "titulo", "descripcion", "piso", "ubicacion", "tipo", "nivel_urgencia",
        "estado", "usuario_correo", "created_at"
    ]
    
    for field in required_fields:
        if field not in body:
            return {
                "statusCode": 400,
                "body": json.dumps({"message": f"Falta el campo obligatorio: {field}"})
            }
    
    if body["tipo"] not in TIPO_ENUM:
        return {
            "statusCode": 400,
            "body": json.dumps({"message": "Valor de 'tipo' no válido"})
        }
    
    if body["nivel_urgencia"] not in NIVEL_URGENCIA_ENUM:
        return {
            "statusCode": 400,
            "body": json.dumps({"message": "Valor de 'nivel_urgencia' no válido"})
        }
    
    if body["estado"] not in ESTADO_ENUM:
        return {
            "statusCode": 400,
            "body": json.dumps({"message": "Valor de 'estado' no válido"})
        }
    
    if body["piso"] not in PISO_RANGO:
        return {
            "statusCode": 400,
            "body": json.dumps({"message": "Valor de 'piso' debe estar entre -2 y 11"})
        }
    
    evidencia_url = None
    if 'evidencias' in body and isinstance(body['evidencias'], list) and len(body['evidencias']) > 0:
        for image_data in body['evidencias']:
            image_url_or_key = None
            if image_data:
                try:
                    key = image_data.get("key")
                    file_b64 = image_data.get("file_base64")
                    content_type = image_data.get("content_type")
                    if not key:
                        return {
                            "statusCode": 400,
                            "body": json.dumps({"message": "Falta 'key' en image"})
                        }
                    if not file_b64:
                        return {
                            "statusCode": 400,
                            "body": json.dumps({"message": "'file_base64' es requerido"})
                        }

                    try:
                        file_bytes = base64.b64decode(file_b64)
                    except Exception as e:
                        return {
                            "statusCode": 400,
                            "body": json.dumps({"message": f"file_base64 inválido: {e}"})
                        }

                    if INCIDENTES_BUCKET:
                        s3.put_object(Bucket=INCIDENTES_BUCKET, Key=key, Body=file_bytes, ContentType=content_type)
                        image_url_or_key = f"s3://{INCIDENTES_BUCKET}/{key}"
                    else:
                        return {
                            "statusCode": 500,
                            "body": json.dumps({"error": "INCIDENTES_BUCKET no configurado"})
                        }
                    
                    evidencia_url = image_url_or_key

                except ClientError as e:
                    code = e.response.get("Error", {}).get("Code")
                    if code == "AccessDenied":
                        return {
                            "statusCode": 403,
                            "body": json.dumps({"error": "Acceso denegado al bucket"})
                        }
                    if code == "NoSuchBucket":
                        return {
                            "statusCode": 400,
                            "body": json.dumps({"error": f"El bucket {INCIDENTES_BUCKET} no existe"})
                        }
                    return {
                        "statusCode": 400,
                        "body": json.dumps({"error": f"Error S3: {e}"})
                    }
                except Exception as e:
                    return {
                        "statusCode": 500,
                        "body": json.dumps({"error": f"Error interno al subir la imagen: {e}"})
                    }
    
    incidente_id = str(uuid.uuid4())
    
    incidente = {
        "incidente_id": incidente_id,
        "titulo": body["titulo"],
        "descripcion": body["descripcion"],
        "piso": body["piso"],
        "ubicacion": body["ubicacion"],
        "tipo": body["tipo"],
        "nivel_urgencia": body["nivel_urgencia"],
        "evidencias": evidencia_url if evidencia_url else body.get("evidencias", []),
        "estado": "reportado",
        "usuario_correo": usuario_autenticado["correo"],
        "created_at": body["created_at"],
        "updated_at": body.get("updated_at", body["created_at"])
    }
    
    try:
        incidente_response = incidentes_table.put_item(Item=incidente)
        return {
            "statusCode": 201,
            "body": json.dumps({
                "message": "Incidente creado correctamente",
                "incidente_id": incidente_id
            })
        }
    except ClientError as e:
        return {
            "statusCode": 500,
            "body": json.dumps({"message": f"Error al crear el incidente: {str(e)}"})
        }
