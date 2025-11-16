import json
import uuid
import os
import boto3
from botocore.exceptions import ClientError 
from decimal import Decimal                  
from datetime import datetime, timezone     

CORS_HEADERS = { "Access-Control-Allow-Origin": "*" }
TABLE_EMPLEADOS_NAME = os.getenv("TABLE_EMPLEADOS", "TABLE_EMPLEADOS")
TABLE_LOGS_NAME = os.getenv("TABLE_LOGS") 

dynamodb = boto3.resource("dynamodb")
empleados_table = dynamodb.Table(TABLE_EMPLEADOS_NAME)
logs_table = dynamodb.Table(TABLE_LOGS_NAME) if TABLE_LOGS_NAME else None

TIPOS_AREA = {"mantenimiento", "electricidad", "limpieza", "seguridad", "ti", "logistica", "otros"}
ESTADOS_VALIDOS = {"activo", "inactivo"}


def _to_dynamodb_numbers(obj):
    """
    Convierte recursivamente int/float -> Decimal.
    Deja bool, None, str, Decimal, etc. tal cual.
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
    Respeta el esquema de logs que definiste.
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
    Crea un log de tipo 'sistema'.
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
    Crea un log de tipo 'auditoria'.
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



def _parse_body(event):
    body = event.get("body", {})
    if isinstance(body, str):
        body = json.loads(body) if body.strip() else {}
    elif not isinstance(body, dict):
        body = {}
    return body

def lambda_handler(event, context):
    registrar_log_sistema(
        nivel="INFO",
        mensaje="Inicio lambda crear empleado",
        servicio="crear_empleado",
        contexto={"request_id": getattr(context, "aws_request_id", None)}
    )

    authorizer = event.get("requestContext", {}).get("authorizer", {})
    rol = authorizer.get("rol")
    correo_actor = authorizer.get("correo")

    if rol not in {"personal_administrativo", "autoridad"}:
        registrar_log_sistema(
            nivel="WARNING",
            mensaje="Usuario sin permiso para crear empleados",
            servicio="crear_empleado",
            contexto={"rol": rol, "correo": correo_actor}
        )
        return {
            "statusCode": 403,
            "headers": CORS_HEADERS,
            "body": json.dumps({"message": "No tienes permiso para crear empleados"})
        }

    body = _parse_body(event)
    nombre = body.get("nombre")
    tipo_area = body.get("tipo_area")
    estado = body.get("estado", "activo")
    contacto = body.get("contacto", {})

    if not nombre or not tipo_area:
        registrar_log_sistema(
            nivel="WARNING",
            mensaje="Faltan campos obligatorios al crear empleado",
            servicio="crear_empleado",
            contexto={"body_recibido": body}
        )
        return {
            "statusCode": 400,
            "headers": CORS_HEADERS,
            "body": json.dumps({"message": "nombre y tipo_area son obligatorios"})
        }

    if tipo_area not in TIPOS_AREA:
        return {
            "statusCode": 400,
            "headers": CORS_HEADERS,
            "body": json.dumps({"message": "tipo_area inválido"})
        }

    if estado not in ESTADOS_VALIDOS:
        return {
            "statusCode": 400,
            "headers": CORS_HEADERS,
            "body": json.dumps({"message": "estado inválido"})
        }

    if contacto and not isinstance(contacto, dict):
        return {
            "statusCode": 400,
            "headers": CORS_HEADERS,
            "body": json.dumps({"message": "contacto debe ser un objeto"})
        }

    empleado = {
        "empleado_id": str(uuid.uuid4()),
        "nombre": nombre,
        "tipo_area": tipo_area,
        "estado": estado,
        "contacto": contacto if contacto else {}
    }

    try:
        empleados_table.put_item(Item=empleado)
    except Exception as e:
        registrar_log_sistema(
            nivel="ERROR",
            mensaje="Error al crear empleado en DynamoDB",
            servicio="crear_empleado",
            contexto={"error": str(e)}
        )
        return {
            "statusCode": 500,
            "headers": CORS_HEADERS,
            "body": json.dumps({"message": f"Error al crear empleado: {str(e)}"})
        }

    registrar_log_auditoria(
        usuario_correo=correo_actor,
        entidad="empleado",
        entidad_id=empleado["empleado_id"],
        operacion="creacion",
        valores_previos={},
        valores_nuevos=empleado
    )

    registrar_log_sistema(
        nivel="INFO",
        mensaje="Empleado creado correctamente",
        servicio="crear_empleado",
        contexto={
            "empleado_id": empleado["empleado_id"],
            "tipo_area": tipo_area,
            "estado": estado,
            "actor": correo_actor,
        }
    )

    return {
        "statusCode": 201,
        "headers": CORS_HEADERS,
        "body": json.dumps({
            "message": "Empleado creado correctamente",
            "empleado": empleado
        })
    }
