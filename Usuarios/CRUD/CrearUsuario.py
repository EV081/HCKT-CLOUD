import json
import boto3
import os
from CRUD.utils import generar_token, validar_token, ALLOWED_ROLES
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail

SENDGRID_API_KEY = os.environ.get("SENDGRID_API_KEY")
EMAIL_FROM = os.environ.get("EMAIL_FROM", "no-reply@example.com")
# -------------------------------------------

TABLE_USUARIOS_NAME = os.getenv("TABLE_USUARIOS", "TABLE_USUARIOS")

dynamodb = boto3.resource("dynamodb")
usuarios_table = dynamodb.Table(TABLE_USUARIOS_NAME)

# --- NUEVO: función para enviar correo de bienvenida ---
def enviar_correo_bienvenida(nombre: str, correo: str):
    """
    Envía un correo de bienvenida usando SendGrid.
    Si falta configuración, solo hace log y no rompe la Lambda.
    """
    if not SENDGRID_API_KEY or not EMAIL_FROM:
        print("SendGrid no configurado (falta SENDGRID_API_KEY o EMAIL_FROM)")
        return

    asunto = "Bienvenido a Alerta UTEC"
    html = f"""
        <p>Hola <strong>{nombre}</strong>,</p>
        <p>¡Bienvenido a la aplicación <strong>Alerta UTEC</strong>! 🎓</p>
        <p>Ya puedes usar la plataforma para registrar tus incidencias.</p>
    """

    message = Mail(
        from_email=EMAIL_FROM,
        to_emails=correo,
        subject=asunto,
        html_content=html
    )

    try:
        sg = SendGridAPIClient(SENDGRID_API_KEY)
        response = sg.send(message)
        print("Correo de bienvenida enviado. Status:", response.status_code)
    except Exception as e:
        # No queremos romper la creación de usuario por un fallo de email
        print("Error al enviar correo de bienvenida:", repr(e))
# -------------------------------------------------------


def lambda_handler(event, context):
    body = {}
    headers = event.get("headers") or {}
    auth_header = headers.get("authorization") or headers.get("Authorization")
    rol_autenticado = None

    if auth_header:
        token = auth_header.split(" ")[-1]
        resultado_token = validar_token(token)
        if not resultado_token.get("valido"):
            return {
                "statusCode": 401,
                "body": json.dumps({"message": resultado_token.get("error", "Token inválido")})
            }
        rol_autenticado = resultado_token.get("rol")

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
        return {
            "statusCode": 400,
            "body": json.dumps({"message": "nombre, correo, contrasena y rol son obligatorios"})
        }

    if "@" not in correo:
        return {
            "statusCode": 400,
            "body": json.dumps({"message": "Correo electrónico inválido"})
        }

    if len(contrasena) < 6:
        return {
            "statusCode": 400,
            "body": json.dumps({"message": "La contraseña debe tener al menos 6 caracteres"})
        }

    if rol not in ALLOWED_ROLES:
        return {
            "statusCode": 400,
            "body": json.dumps({"message": "Rol inválido, debe ser 'estudiante', 'personal_administrativo' o 'autoridad'"})
        }

    if not rol_autenticado:
        if rol != "estudiante":
            return {
                "statusCode": 403,
                "body": json.dumps({"message": "Solo puedes auto-registrarte como estudiante"})
            }
    elif rol_autenticado != "autoridad":
        return {
            "statusCode": 403,
            "body": json.dumps({"message": "Solo una autoridad puede crear usuarios adicionales"})
        }

    resp = usuarios_table.get_item(Key={"correo": correo})
    if "Item" in resp:
        return {
            "statusCode": 400,
            "body": json.dumps({"error": "El correo ya está registrado"})
        }

    item = {
        "nombre": nombre,
        "correo": correo,
        "contrasena": contrasena,
        "rol": rol
    }

    usuarios_table.put_item(Item=item)

    # --- NUEVO: enviar correo de bienvenida ---
    enviar_correo_bienvenida(nombre=nombre, correo=correo)
    # ------------------------------------------

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

    return {
        "statusCode": 201,
        "body": json.dumps(respuesta)
    }
