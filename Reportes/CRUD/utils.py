import jwt
import os
from datetime import datetime, timedelta

# Solo necesitamos JWT_SECRET, no tablas de DynamoDB
JWT_SECRET = os.getenv("JWT_SECRET", "sera_que_y@r1tz@_me_hace_caso")
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_HOURS = int(os.getenv("JWT_EXPIRATION_HOURS", "24"))


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