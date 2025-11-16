import os
import jwt
from datetime import datetime, timedelta

JWT_SECRET = os.getenv("JWT_SECRET", "")
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_HOURS = int(os.getenv("JWT_EXPIRATION_HOURS", "24"))

def validar_token(token: str):
    if not token:
        return {"valido": False, "error": "Token es obligatorio"}

    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        expiracion = payload.get("exp")
        if expiracion and datetime.utcnow() > datetime.utcfromtimestamp(expiracion):
            return {"valido": False, "error": "Token expirado"}
        return {
            "valido": True,
            "correo": payload.get("correo"),
            "rol": payload.get("rol"),
            "nombre": payload.get("nombre", "")
        }
    except jwt.ExpiredSignatureError:
        return {"valido": False, "error": "Token expirado"}
    except jwt.InvalidTokenError:
        return {"valido": False, "error": "Token inválido"}
