import os
import json
import uuid
import base64
import boto3
from datetime import datetime, timezone
from CRUD.utils import validar_token
from botocore.exceptions import ClientError
from decimal import Decimal, InvalidOperation

dynamodb = boto3.resource('dynamodb')
s3 = boto3.client('s3')
table_name = os.environ.get('TABLE_INCIDENTES')
incidentes_table = dynamodb.Table(table_name)
INCIDENTES_BUCKET = os.environ.get('INCIDENTES_BUCKET')

TIPO_ENUM = ["limpieza", "TI" ,"seguridad", "mantenimiento", "otro"]
NIVEL_URGENCIA_ENUM = ["bajo", "medio", "alto", "critico"]
ESTADO_ENUM = ["reportado", "en_progreso", "resuelto"]
PISO_RANGO = range(-2, 12)

def _to_dynamodb_numbers(obj):
    """
    Convierte recursivamente int/float -> Decimal.
    Deja bool, None, str, Decimal, etc. tal cual.
    Evita el error 'Float types are not supported'.
    """
    if isinstance(obj, dict):
        return {k: _to_dynamodb_numbers(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_to_dynamodb_numbers(x) for x in obj]
    if isinstance(obj, bool) or obj is None:
        return obj
    if isinstance(obj, Decimal):
        return obj
    if isinstance(obj, (int, float)):
        return Decimal(str(obj))
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
    
    if usuario_autenticado["rol"] not in ["estudiante", "personal_administrativo"]:
        return {
            "statusCode": 403,
            "body": json.dumps({"message": "No tienes permisos para crear un incidente"})
        }
    
    # 👇 IMPORTANTE: parse_float=Decimal para que no se creen floats
    body = json.loads(event.get('body') or '{}', parse_float=Decimal)
    
    required_fields = [
        "titulo", "descripcion", "piso", "ubicacion", "tipo", "nivel_urgencia"
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

    # Normalizar piso
    try:
        piso_val = int(body["piso"])
    except (TypeError, ValueError):
        return {
            "statusCode": 400,
            "body": json.dumps({"message": "El campo 'piso' debe ser un número entero"})
        }

    if piso_val not in PISO_RANGO:
        return {
            "statusCode": 400,
            "body": json.dumps({"message": "Valor de 'piso' debe estar entre -2 y 11"})
        }

    # Coordenadas opcionales
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
            lat = Decimal(str(coordenadas["lat"]))
            lng = Decimal(str(coordenadas["lng"]))
        except (InvalidOperation, TypeError, ValueError):
            return {
                "statusCode": 400,
                "body": json.dumps({"message": "'lat' y 'lng' deben ser números válidos"})
            }

    incidente_id = str(uuid.uuid4())
    created_at = datetime.now(timezone.utc).isoformat()
    
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
    
    incidente = {
        "incidente_id": incidente_id,
        "titulo": body["titulo"],
        "descripcion": body["descripcion"],
        "piso": piso_val,
        "ubicacion": body["ubicacion"],   # aquí puede venir x/y con decimales
        "tipo": body["tipo"],
        "nivel_urgencia": body["nivel_urgencia"],
        "evidencias": [evidencia_url] if evidencia_url else [],
        "estado": "reportado",
        "usuario_correo": usuario_autenticado["correo"],
        "created_at": created_at,
        "updated_at": created_at
    }

    if coordenadas is not None:
        incidente["coordenadas"] = {
            "lat": lat,
            "lng": lng
        }

    # 👇 ÚLTIMO PASO CLAVE: convertir cualquier int/float a Decimal (ubicacion.x/y, etc.)
    incidente = _to_dynamodb_numbers(incidente)
    
    try:
        incidentes_table.put_item(Item=incidente)
        return {
            "statusCode": 201,
            "body": json.dumps({
                "message": "Incidente creado correctamente",
                "incidente_id": incidente_id
            })
        }
    except ClientError as e:
        # Aquí también puedes loguear el item si quieres debug extra:
        # print("ITEM QUE ROMPE:", incidente)
        return {
            "statusCode": 500,
            "body": json.dumps({"message": f"Error al crear el incidente: {str(e)}"})
        }
