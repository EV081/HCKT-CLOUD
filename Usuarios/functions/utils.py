import jwt
import os
from datetime import datetime, timedelta

JWT_SECRET = os.getenv("JWT_SECRET", "qwertyuiopmnbvcxz12345lkjh09876gfd4567sa1234")
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_HOURS = int(os.getenv("JWT_EXPIRATION_HOURS", "24"))


def generar_token(correo, role, nombre):
    """
    Genera un JWT como Spring Boot
    """
    payload = {
        "correo": correo,
        "role": role,
        "nombre": nombre,
        "iat": datetime.utcnow(),
        "exp": datetime.utcnow() + timedelta(hours=JWT_EXPIRATION_HOURS)
    }
    
    token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
    return token


def validar_token(token):
    """
    Valida un JWT y retorna información del usuario
    
    Returns:
        dict: {
            "valido": bool,
            "correo": str,
            "role": str,
            "nombre": str,
            "error": str (opcional)
        }
    """
    if not token:
        return {"valido": False, "error": "Token es obligatorio"}

    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        
        return {
            "valido": True,
            "correo": payload.get("correo"),
            "role": payload.get("role", "Cliente"),
            "nombre": payload.get("nombre", "")
        }
    except jwt.ExpiredSignatureError:
        return {"valido": False, "error": "Token expirado"}
    except jwt.InvalidTokenError:
        return {"valido": False, "error": "Token inválido"}


def verificar_rol(usuario_autenticado, roles_permitidos):
    """
    Verifica si el usuario tiene uno de los roles permitidos
    
    Args:
        usuario_autenticado: dict con 'role' del token
        roles_permitidos: list de roles permitidos, ej: ["Admin", "Gerente"]
    
    Returns:
        bool: True si tiene permiso
    """
    role_usuario = usuario_autenticado.get("role")
    return role_usuario in roles_permitidos