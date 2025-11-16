import json
import boto3
import os
import requests
from CRUD.utils import generar_token, validar_token, ALLOWED_ROLES
from botocore.exceptions import ClientError  
from decimal import Decimal                  
import uuid                                  

CORS_HEADERS = {"Access-Control-Allow-Origin": "*"}

BREVO_API_KEY = os.environ.get("BREVO_API_KEY")
EMAIL_FROM = os.environ.get("EMAIL_FROM", "no-reply@example.com")

TABLE_USUARIOS_NAME = os.getenv("TABLE_USUARIOS", "TABLE_USUARIOS")

dynamodb = boto3.resource("dynamodb")
usuarios_table = dynamodb.Table(TABLE_USUARIOS_NAME)

TABLE_LOGS_NAME = os.getenv("TABLE_LOGS")
logs_table = dynamodb.Table(TABLE_LOGS_NAME) if TABLE_LOGS_NAME else None

def _response(status_code, body_dict):
    """
    Helper para unificar respuestas HTTP con CORS.
    """
    return {
        "statusCode": status_code,
        "headers": CORS_HEADERS,
        "body": json.dumps(body_dict)
    }


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
        "marca_tiempo": __import__("datetime").datetime.now(
            __import__("datetime").timezone.utc
        ).isoformat(),
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
        "marca_tiempo": __import__("datetime").datetime.now(
            __import__("datetime").timezone.utc
        ).isoformat(),
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


def enviar_correo_bienvenida(nombre: str, correo: str):
    """
    Envía un correo de bienvenida usando Brevo (Sendinblue) vía API HTTP.
    Si falta configuración, solo hace log y no rompe la Lambda.
    """
    if not BREVO_API_KEY or not EMAIL_FROM:
        msg = "Brevo no configurado (falta BREVO_API_KEY o EMAIL_FROM)"
        print(msg)
        registrar_log_sistema(
            nivel="WARNING",
            mensaje="No se pudo enviar correo de bienvenida por falta de configuración Brevo",
            servicio="crear_usuario",
            contexto={"correo": correo}
        )
        return

    asunto = "🎓 Bienvenido a Alerta UTEC"

    html = f"""
        <div style="font-family: Arial, sans-serif; font-size: 14px; color: #222;">
            <p>Hola <strong>{nombre}</strong>,</p>

            <p>
                ¡Gracias por registrarte en <strong>Alerta UTEC</strong>! 🎓<br/>
                Desde ahora puedes usar la plataforma para reportar incidencias dentro del campus
                y ayudarnos a mantener un entorno más seguro y ordenado.
            </p>

            <p><strong>¿Qué puedes hacer con Alerta UTEC?</strong></p>
            <ul>
                <li>Registrar incidencias de limpieza, TI, seguridad y mantenimiento.</li>
                <li>Indicar la ubicación exacta del problema.</li>
                <li>Adjuntar evidencias para que el equipo pueda atender más rápido tu solicitud.</li>
            </ul>

            <p>
                Te invitamos a ingresar a la app y registrar tu primera incidencia cuando lo necesites.
            </p>

            <p style="margin-top: 24px;">
                Saludos,<br/>
                <strong>Equipo Alerta UTEC</strong>
            </p>

            <hr style="border: none; border-top: 1px solid #ddd; margin-top: 24px;"/>

            <p style="font-size: 12px; color: #777;">
                Este es un correo automático, por favor no lo respondas.
            </p>
        </div>
    """

    url = "https://api.brevo.com/v3/smtp/email"
    payload = {
        "sender": {"email": EMAIL_FROM},
        "to": [{"email": correo}],
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
        print("Correo de bienvenida enviado. Status:", resp.status_code, "Body:", resp.text)
        registrar_log_sistema(
            nivel="INFO",
            mensaje="Correo de bienvenida enviado",
            servicio="crear_usuario",
            contexto={"correo": correo, "status_code": resp.status_code}
        )
    except Exception as e:
        print("Error al enviar correo de bienvenida:", repr(e))
        registrar_log_sistema(
            nivel="ERROR",
            mensaje="Error al enviar correo de bienvenida",
            servicio="crear_usuario",
            contexto={"correo": correo, "error": repr(e)}
        )


def lambda_handler(event, context):
    registrar_log_sistema(
        nivel="INFO",
        mensaje="Inicio lambda crear usuario",
        servicio="crear_usuario",
        contexto={"request_id": getattr(context, "aws_request_id", None)}
    )

    body = {}
    headers = event.get("headers") or {}
    auth_header = headers.get("authorization") or headers.get("Authorization")
    rol_autenticado = None
    correo_autenticado = None

    if auth_header:
        token = auth_header.split(" ")[-1]
        resultado_token = validar_token(token)
        if not resultado_token.get("valido"):
            registrar_log_sistema(
                nivel="WARNING",
                mensaje="Token inválido al crear usuario",
                servicio="crear_usuario",
                contexto={"motivo": resultado_token.get("error")}
            )
            return _response(401, {"message": resultado_token.get("error", "Token inválido")})
        
        rol_autenticado = resultado_token.get("rol")
        correo_autenticado = resultado_token.get("correo")

    if isinstance(event, dict) and "body" in event:
        raw_body = event.get("body")
        if isinstance(raw_body, str):
            body = json.loads(raw_body) if raw_body else {}
        elif isinstance(raw_body, dict):
            body = raw_body
    elif isinstance(event, dict):
        body = event
    elif isinstance(event, str):
        body = json.loads(event)

    nombre = body.get("nombre")
    correo = body.get("correo")
    contrasena = body.get("contrasena")
    rol = body.get("rol", "estudiante")

    if not nombre or not correo or not contrasena or not rol:
        registrar_log_sistema(
            nivel="WARNING",
            mensaje="Campos obligatorios faltantes al crear usuario",
            servicio="crear_usuario",
            contexto={"body_recibido": body}
        )
        return _response(
            400,
            {"message": "nombre, correo, contrasena y rol son obligatorios"}
        )

    if "@" not in correo:
        return _response(400, {"message": "Correo electrónico inválido"})

    if len(contrasena) < 6:
        return _response(400, {"message": "La contraseña debe tener al menos 6 caracteres"})

    if rol not in ALLOWED_ROLES:
        return _response(
            400,
            {"message": "Rol inválido, debe ser 'estudiante', 'personal_administrativo' o 'autoridad'"}
        )

    if not rol_autenticado:
        if rol != "estudiante":
            registrar_log_sistema(
                nivel="WARNING",
                mensaje="Intento de auto-registro con rol no permitido",
                servicio="crear_usuario",
                contexto={"correo": correo, "rol_solicitado": rol}
            )
            return _response(
                403,
                {"message": "Solo puedes auto-registrarte como estudiante"}
            )
    elif rol_autenticado != "autoridad":
        registrar_log_sistema(
            nivel="WARNING",
            mensaje="Usuario sin permiso para crear usuarios adicionales",
            servicio="crear_usuario",
            contexto={
                "correo_autenticado": correo_autenticado,
                "rol_autenticado": rol_autenticado,
                "rol_solicitado": rol
            }
        )
        return _response(
            403,
            {"message": "Solo una autoridad puede crear usuarios adicionales"}
        )

    try:
        resp = usuarios_table.get_item(Key={"correo": correo})
    except ClientError as e:
        registrar_log_sistema(
            nivel="ERROR",
            mensaje="Error al consultar usuario en DynamoDB",
            servicio="crear_usuario",
            contexto={"correo": correo, "error": str(e)}
        )
        return _response(500, {"message": "Error interno al verificar usuario"})

    if "Item" in resp:
        registrar_log_sistema(
            nivel="WARNING",
            mensaje="Intento de registro con correo ya existente",
            servicio="crear_usuario",
            contexto={"correo": correo}
        )
        return _response(400, {"error": "El correo ya está registrado"})

    item = {
        "nombre": nombre,
        "correo": correo,
        "contrasena": contrasena,
        "rol": rol
    }

    try:
        usuarios_table.put_item(Item=item)
    except ClientError as e:
        registrar_log_sistema(
            nivel="ERROR",
            mensaje="Error al guardar usuario en DynamoDB",
            servicio="crear_usuario",
            contexto={"correo": correo, "error": str(e)}
        )
        return _response(500, {"message": "Error interno al crear el usuario"})

    actor_correo = correo_autenticado or correo
    registrar_log_auditoria(
        usuario_correo=actor_correo,
        entidad="usuario",
        entidad_id=correo,
        operacion="creacion",
        valores_previos={},
        valores_nuevos=item
    )

    registrar_log_sistema(
        nivel="INFO",
        mensaje="Usuario creado correctamente",
        servicio="crear_usuario",
        contexto={
            "correo_creado": correo,
            "rol_creado": rol,
            "actor": actor_correo
        }
    )

    enviar_correo_bienvenida(nombre=nombre, correo=correo)
    
    respuesta = {
        "message": "Usuario creado correctamente",
        "usuario": {
            "correo": correo,
            "nombre": nombre,
            "rol": rol
        }
    }

    if not rol_autenticado:
        respuesta["token"] = generar_token(correo=correo, role=rol, nombre=nombre)

    return _response(201, respuesta)
