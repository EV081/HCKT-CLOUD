import os
import json
import base64
import boto3
from datetime import datetime, timezone
from CRUD.utils import validar_token
from botocore.exceptions import ClientError

dynamodb = boto3.resource('dynamodb')
s3 = boto3.client('s3')
table_name = os.environ.get('TABLE_INCIDENTES')
incidentes_table = dynamodb.Table(table_name)
INCIDENTES_BUCKET = os.environ.get('INCIDENTES_BUCKET')

TIPO_ENUM = ["limpieza", "TI" ,"seguridad", "mantenimiento", "otro"]
NIVEL_URGENCIA_ENUM = ["bajo", "medio", "alto", "critico"]
PISO_RANGO = range(-2, 12)

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

    if usuario_autenticado["rol"] != "estudiante":
        return {
            "statusCode": 403,
            "body": json.dumps({"message": "No tienes permisos para actualizar un incidente"})
        }

    body = json.loads(event.get('body', '{}'))

    incidente_id = body.get("incidente_id")
    if not incidente_id:
        return {
            "statusCode": 400,
            "body": json.dumps({"message": "Falta 'incidente_id' en el body"})
        }

    required_fields = [
        "incidente_id",
        "titulo",
        "descripcion",
        "piso",
        "ubicacion",
        "tipo",
        "nivel_urgencia"
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

    if body["piso"] not in PISO_RANGO:
        return {
            "statusCode": 400,
            "body": json.dumps({"message": "Valor de 'piso' debe estar entre -2 y 11"})
        }

    coordenadas = body.get("coordenadas")
    lat = lng = None

    if coordenadas is not None:
        if not isinstance(coordenadas, dict):
            return {
                "statusCode": 400,
                "body": json.dumps({"message": "'coordenadas' debe ser un objeto con 'lat' y 'lng'"})
            }
        
        if "lat" not in coordenadas or "lng" not in coordenadas:
            return {
                "statusCode": 400,
                "body": json.dumps({"message": "'coordenadas' debe incluir 'lat' y 'lng'"})
            }
        
        try:
            lat = float(coordenadas["lat"])
            lng = float(coordenadas["lng"])
        except (TypeError, ValueError):
            return {
                "statusCode": 400,
                "body": json.dumps({"message": "'lat' y 'lng' deben ser números"})
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

    if incidente_actual.get("usuario_correo") != usuario_autenticado["correo"]:
        return {
            "statusCode": 403,
            "body": json.dumps({"message": "Solo puedes actualizar tus propios incidentes"})
        }

    evidencia_url = None
    if 'evidencias' in body and body['evidencias'] is not None:
        image_data = body['evidencias']

        if not isinstance(image_data, dict):
            return {
                "statusCode": 400,
                "body": json.dumps({"message": "'evidencias' debe ser un objeto con 'file_base64'"})
            }

        file_b64 = image_data.get("file_base64")
        if not file_b64:
            return {
                "statusCode": 400,
                "body": json.dumps({"message": "'file_base64' es requerido en 'evidencias'"})
            }

        try:
            file_bytes = base64.b64decode(file_b64)
        except Exception as e:
            return {
                "statusCode": 400,
                "body": json.dumps({"message": f"file_base64 inválido: {e}"})
            }

        if not INCIDENTES_BUCKET:
            return {
                "statusCode": 500,
                "body": json.dumps({"error": "INCIDENTES_BUCKET no configurado"})
            }

        key = f"evidencia_{incidente_id}"
        content_type = "image/png"

        try:
            s3.put_object(
                Bucket=INCIDENTES_BUCKET,
                Key=key,
                Body=file_bytes,
               ContentType=content_type
            )
            evidencia_url = f"s3://{INCIDENTES_BUCKET}/{key}"
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

    incidente_actual.update({
        "titulo": body["titulo"],
        "descripcion": body["descripcion"],
        "piso": body["piso"],
        "ubicacion": body["ubicacion"],
        "tipo": body["tipo"],
        "nivel_urgencia": body["nivel_urgencia"],
        "evidencias": [evidencia_url] if evidencia_url else incidente_actual.get("evidencias", []),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    })

    if coordenadas is not None:
        incidente_actual["coordenadas"] = {
            "lat": lat,
            "lng": lng
        }

    try:
        incidentes_table.put_item(Item=incidente_actual)
        return {
            "statusCode": 200,
            "body": json.dumps({
                "message": "Incidente actualizado correctamente",
                "incidente_id": incidente_id
            })
        }
    except ClientError as e:
        return {
            "statusCode": 500,
            "body": json.dumps({"message": f"Error al actualizar el incidente: {str(e)}"})
        }
