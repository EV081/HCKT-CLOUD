import os
import json
from datetime import datetime, timezone
import boto3
from CRUD.utils import validar_token
from botocore.exceptions import ClientError
from decimal import Decimal
import uuid
import requests


dynamodb = boto3.resource('dynamodb')
table_name = os.environ.get('TABLE_INCIDENTES')
incidentes_table = dynamodb.Table(table_name)

logs_table_name = os.environ.get('TABLE_LOGS')
logs_table = dynamodb.Table(logs_table_name) if logs_table_name else None

ESTADO_ENUM = ["reportado", "en_progreso", "resuelto"]
ADMIN_ESTADOS_PERMITIDOS = ["en_progreso", "resuelto"]

BREVO_API_KEY = os.environ.get("BREVO_API_KEY")
EMAIL_FROM = os.environ.get("EMAIL_FROM", "no-reply@example.com")


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



def enviar_correo_cambio_estado(correo_destino, incidente, estado_nuevo):
    """
    Envía un correo al creador de la incidencia cada vez que cambia el estado.
    No rompe la Lambda si falla el envío.
    """
    if not correo_destino:
        print("Incidente sin usuario_correo, no se puede enviar notificación de estado.")
        return

    if not BREVO_API_KEY or not EMAIL_FROM:
        print("Brevo no configurado (falta BREVO_API_KEY o EMAIL_FROM)")
        return

    estado_legible = {
        "reportado": "reportado",
        "en_progreso": "en progreso",
        "resuelto": "resuelto"
    }.get(estado_nuevo, estado_nuevo)

    asunto = "Actualización de tu incidencia - Alerta UTEC"

    html = f"""
        <p>Hola,</p>
        <p>Te informamos que el estado de tu incidencia en <strong>Alerta UTEC</strong> ha cambiado.</p>
        <p><strong>Nuevo estado:</strong> {estado_legible.upper()}</p>
        <p><strong>Detalle de la incidencia:</strong></p>
        <ul>
            <li><strong>Título:</strong> {incidente.get("titulo")}</li>
            <li><strong>Código de seguimiento:</strong> {incidente.get("incidente_id")}</li>
        </ul>
        <p>Gracias por usar la plataforma para reportar incidencias en UTEC. 🏫</p>
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
            "Correo de cambio de estado enviado. Status:",
            resp.status_code,
            "Body:",
            resp.text,
        )
    except Exception as e:
        print("Error al enviar correo de cambio de estado:", repr(e))


def lambda_handler(event, context):
    registrar_log_sistema(
        nivel="INFO",
        mensaje="Inicio lambda cambiar estado de incidente",
        servicio="cambiar_estado_incidencia",
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
            mensaje="Token inválido al cambiar estado de incidente",
            servicio="cambiar_estado_incidencia",
            contexto={"motivo": resultado_validacion.get("error")}
        )
        return {
            "statusCode": 401,
            "body": json.dumps({"message": resultado_validacion.get("error")})
        }
    
    usuario_autenticado = {
        "correo": resultado_validacion.get("correo"),
        "rol": resultado_validacion.get("rol")
    }
    
    if usuario_autenticado["rol"] not in ["personal_administrativo", "autoridad"]:
        registrar_log_sistema(
            nivel="WARNING",
            mensaje="Usuario sin permiso para cambiar estado de incidente",
            servicio="cambiar_estado_incidencia",
            contexto={
                "correo": usuario_autenticado["correo"],
                "rol": usuario_autenticado["rol"]
            }
        )
        return {
            "statusCode": 403,
            "body": json.dumps({"message": "Solo un administrador puede cambiar el estado del incidente"})
        }

    body = json.loads(event.get('body', '{}'))
    
    incidente_id = body.get('incidente_id')
    if not incidente_id:
        registrar_log_sistema(
            nivel="WARNING",
            mensaje="Falta 'incidente_id' en el body",
            servicio="cambiar_estado_incidencia",
            contexto={"body_recibido": body}
        )
        return {
            "statusCode": 400,
            "body": json.dumps({"message": "Falta 'incidente_id' en el body"})
        }

    if "estado" not in body:
        registrar_log_sistema(
            nivel="WARNING",
            mensaje="Falta 'estado' en el body",
            servicio="cambiar_estado_incidencia",
            contexto={"body_recibido": body}
        )
        return {
            "statusCode": 400,
            "body": json.dumps({"message": "Falta 'estado' en el body"})
        }

    estado_nuevo = body["estado"]

    if estado_nuevo not in ESTADO_ENUM or estado_nuevo not in ADMIN_ESTADOS_PERMITIDOS:
        registrar_log_sistema(
            nivel="WARNING",
            mensaje="Estado no permitido para Admin",
            servicio="cambiar_estado_incidencia",
            contexto={"estado_recibido": estado_nuevo}
        )
        return {
            "statusCode": 400,
            "body": json.dumps({"message": "El estado debe ser 'en_progreso' o 'resuelto' para Admin"})
        }

    try:
        response = incidentes_table.get_item(Key={'incidente_id': incidente_id})
        if 'Item' not in response:
            registrar_log_sistema(
                nivel="WARNING",
                mensaje="Incidente no encontrado al cambiar estado",
                servicio="cambiar_estado_incidencia",
                contexto={"incidente_id": incidente_id}
            )
            return {
                "statusCode": 404,
                "body": json.dumps({"message": "Incidente no encontrado"})
            }
        
        incidente_actual = response['Item']
        incidente_prev = dict(incidente_actual)
    except ClientError as e:
        registrar_log_sistema(
            nivel="ERROR",
            mensaje="Error al obtener incidente de DynamoDB",
            servicio="cambiar_estado_incidencia",
            contexto={"incidente_id": incidente_id, "error": str(e)}
        )
        return {
            "statusCode": 500,
            "body": json.dumps({"message": f"Error al obtener el incidente: {str(e)}"})
        }

    incidente_nuevo = dict(incidente_actual)
    incidente_nuevo["estado"] = estado_nuevo
    incidente_nuevo["updated_at"] = datetime.now(timezone.utc).isoformat()
    
    try:
        incidentes_table.put_item(Item=incidente_nuevo)

        registrar_log_auditoria(
            usuario_correo=usuario_autenticado["correo"],
            entidad="incidente",
            entidad_id=incidente_id,
            operacion="actualizacion",
            valores_previos=incidente_prev,
            valores_nuevos=incidente_nuevo
        )

        registrar_log_sistema(
            nivel="INFO",
            mensaje="Estado de incidente actualizado correctamente",
            servicio="cambiar_estado_incidencia",
            contexto={
                "incidente_id": incidente_id,
                "nuevo_estado": estado_nuevo,
                "admin_correo": usuario_autenticado["correo"]
            }
        )

        correo_creador = incidente_nuevo.get("usuario_correo")
        enviar_correo_cambio_estado(
            correo_destino=correo_creador,
            incidente=incidente_nuevo,
            estado_nuevo=estado_nuevo
        )

        return {
            "statusCode": 200,
            "body": json.dumps({
                "message": "Estado actualizado correctamente",
                "incidente_id": incidente_id,
                "nuevo_estado": estado_nuevo
            })
        }
    except ClientError as e:
        registrar_log_sistema(
            nivel="ERROR",
            mensaje="Error al actualizar incidente en DynamoDB",
            servicio="cambiar_estado_incidencia",
            contexto={"incidente_id": incidente_id, "error": str(e)}
        )
        return {
            "statusCode": 500,
            "body": json.dumps({"message": f"Error al actualizar el incidente: {str(e)}"})
        }
