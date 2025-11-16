import os
import json
import uuid
import base64
import boto3
from datetime import datetime, timezone
from CRUD.utils import validar_token
from botocore.exceptions import ClientError
from decimal import Decimal, InvalidOperation
import requests  # NUEVO

dynamodb = boto3.resource('dynamodb')
s3 = boto3.client('s3')

table_name = os.environ.get('TABLE_INCIDENTES')
incidentes_table = dynamodb.Table(table_name)
INCIDENTES_BUCKET = os.environ.get('INCIDENTES_BUCKET')

logs_table_name = os.environ.get('TABLE_LOGS')
logs_table = dynamodb.Table(logs_table_name) if logs_table_name else None

BREVO_API_KEY = os.environ.get("BREVO_API_KEY")
EMAIL_FROM = os.environ.get("EMAIL_FROM", "no-reply@example.com")

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


def _guardar_log_en_dynamodb(registro):
    """
    Guarda el registro en la tabla de logs y lo imprime para CloudWatch.
    Respeta el esquema de logs.
    """
    if not logs_table:
        print("[LOG_WARNING] TABLE_LOGS no configurada, no se persiste el log.")
        print("[LOG]", json.dumps(registro, default=str))
        return

    registro_ddb = _to_dynamodb_numbers(registro)

    print("[LOG]", json.dumps(registro_ddb, default=str))

    try:
        logs_table.put_item(Item=registro_ddb)
    except ClientError as e:
        print("[LOG_ERROR] Error al guardar log en DynamoDB:", repr(e))


def registrar_log_sistema(nivel, mensaje, servicio, contexto=None):
    """
    Crea un log de tipo 'sistema' siguiendo el esquema.
    nivel: INFO | WARNING | ERROR | CRITICAL | AUDIT
    """
    if contexto is None:
        contexto = {}

    registro = {
        "registro_id": str(uuid.uuid4()),
        "nivel": nivel,
        "tipo": "sistema",
        "marca_tiempo": datetime.now(timezone.utc).isoformat(),
        "detalles_sistema": {
            "mensaje": mensaje,
            "servicio": servicio,
            "contexto": contexto
        }
    }

    _guardar_log_en_dynamodb(registro)


def registrar_log_auditoria(
    usuario_correo,
    entidad,
    entidad_id,
    operacion,
    valores_previos=None,
    valores_nuevos=None,
    nivel="AUDIT"
):
    """
    Crea un log de tipo 'auditoria' siguiendo el esquema.
    operacion: creacion | actualizacion | eliminacion | consulta
    """
    if valores_previos is None:
        valores_previos = {}
    if valores_nuevos is None:
        valores_nuevos = {}

    registro = {
        "registro_id": str(uuid.uuid4()),
        "nivel": nivel,
        "tipo": "auditoria",
        "marca_tiempo": datetime.now(timezone.utc).isoformat(),
        "detalles_auditoria": {
            "usuario_correo": usuario_correo,
            "entidad": entidad,
            "entidad_id": entidad_id,
            "operacion": operacion,
            "valores_previos": valores_previos,
            "valores_nuevos": valores_nuevos,
        }
    }

    _guardar_log_en_dynamodb(registro)


def enviar_correo_incidencia(correo_destino, nombre, incidente):
    """
    Envía un correo al usuario indicando que su incidencia fue registrada.
    No rompe la Lambda si falla el envío.
    """
    if not BREVO_API_KEY or not EMAIL_FROM:
        print("Brevo no configurado (falta BREVO_API_KEY o EMAIL_FROM)")
        return

    asunto = "Hemos recibido tu incidencia - Alerta UTEC"

    if nombre:
        saludo = f"Hola <strong>{nombre}</strong>,"
    else:
        saludo = "Hola,"

    html = f"""
        <p>{saludo}</p>
        <p>Hemos recibido correctamente tu incidencia en la aplicación <strong>Alerta UTEC</strong> ✅.</p>
        <p>En los próximos momentos nuestro equipo revisará el caso y comenzará a atenderlo.</p>
        <p><strong>Resumen de la incidencia:</strong></p>
        <ul>
            <li><strong>Título:</strong> {incidente.get("titulo")}</li>
            <li><strong>Tipo:</strong> {incidente.get("tipo")}</li>
            <li><strong>Nivel de urgencia:</strong> {incidente.get("nivel_urgencia")}</li>
            <li><strong>Código de seguimiento:</strong> {incidente.get("incidente_id")}</li>
        </ul>
        <p>Gracias por ayudarnos a mantener UTEC segura y en buen estado. 🏫</p>
        <p><em>Por favor, no respondas a este correo. Ha sido generado automáticamente.</em></p>
    """

    url = "https://api.brevo.com/v3/smtp/email"
    payload = {
        "sender": {"email": EMAIL_FROM},
        "to": [{"email": correo_destino}],
        "subject": asunto,
        "htmlContent": html,
    }
    headers = {
        "accept": "application/json",
        "content-type": "application/json",
        "api-key": BREVO_API_KEY,
    }

    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=10)
        print(
            "Correo de incidencia enviado. Status:",
            resp.status_code,
            "Body:",
            resp.text,
        )
    except Exception as e:
        print("Error al enviar correo de incidencia:", repr(e))


def lambda_handler(event, context):
    registrar_log_sistema(
        nivel="INFO",
        mensaje="Inicio lambda crear incidencia",
        servicio="crear_incidencia",
        contexto={"request_id": getattr(context, "aws_request_id", None)}
    )

    headers = event.get("headers") or {}
    auth_header = headers.get("Authorization") or headers.get("authorization") or ""
    if auth_header.lower().startswith("bearer "):
        auth_header = auth_header.split(" ", 1)[1].strip()
    token = auth_header
    
    resultado_validacion = validar_token(token)
    
    if not resultado_validacion.get("valido"):
        registrar_log_sistema(
            nivel="WARNING",
            mensaje="Token inválido al crear incidencia",
            servicio="crear_incidencia",
            contexto={"motivo": resultado_validacion.get("error")}
        )
        return {
            "statusCode": 401,
            "body": json.dumps({"message": resultado_validacion.get("error")})
        }
    
    usuario_autenticado = {
        "correo": resultado_validacion.get("correo"),
        "rol": resultado_validacion.get("rol"),
        "nombre": resultado_validacion.get("nombre")
    }
    
    if usuario_autenticado["rol"] not in ["estudiante", "personal_administrativo"]:
        registrar_log_sistema(
            nivel="WARNING",
            mensaje="Usuario sin permiso para crear incidente",
            servicio="crear_incidencia",
            contexto={"correo": usuario_autenticado["correo"], "rol": usuario_autenticado["rol"]}
        )
        return {
            "statusCode": 403,
            "body": json.dumps({"message": "No tienes permisos para crear un incidente"})
        }
    
    body = json.loads(event.get('body') or '{}', parse_float=Decimal)
    
    required_fields = [
        "titulo", "descripcion", "piso", "ubicacion", "tipo", "nivel_urgencia"
    ]
    
    for field in required_fields:
        if field not in body:
            registrar_log_sistema(
                nivel="WARNING",
                mensaje=f"Falta campo obligatorio: {field}",
                servicio="crear_incidencia",
                contexto={"body_recibido": body}
            )
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
        "ubicacion": body["ubicacion"],
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

    incidente_ddb = _to_dynamodb_numbers(incidente)
    
    try:
        incidentes_table.put_item(Item=incidente_ddb)

        registrar_log_auditoria(
            usuario_correo=usuario_autenticado["correo"],
            entidad="incidente",
            entidad_id=incidente_id,
            operacion="creacion",
            valores_previos={},
            valores_nuevos=incidente
        )

        registrar_log_sistema(
            nivel="INFO",
            mensaje="Incidente creado correctamente",
            servicio="crear_incidencia",
            contexto={
                "incidente_id": incidente_id,
                "usuario_correo": usuario_autenticado["correo"],
                "tipo": body["tipo"],
                "nivel_urgencia": body["nivel_urgencia"]
            }
        )

        enviar_correo_incidencia(
            correo_destino=usuario_autenticado["correo"],
            nombre=usuario_autenticado.get("nombre"),
            incidente=incidente
        )

        return {
            "statusCode": 201,
            "body": json.dumps({
                "message": "Incidencia registrada correctamente. En breve comenzaremos a atenderla.",
                "incidente_id": incidente_id
            })
        }
    except ClientError as e:
        registrar_log_sistema(
            nivel="ERROR",
            mensaje="Error al crear el incidente en DynamoDB",
            servicio="crear_incidencia",
            contexto={
                "incidente_id": incidente_id,
                "error": str(e)
            }
        )
        return {
            "statusCode": 500,
            "body": json.dumps({"message": f"Error al crear el incidente: {str(e)}"})
        }
