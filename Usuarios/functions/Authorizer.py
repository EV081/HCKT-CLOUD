import json
from Usuarios.functions.utils import validar_token

def lambda_handler(event, context):
    """
    Lambda Authorizer con validación de JWT
    """
    token = event.get("authorizationToken", "")
    
    if token.lower().startswith("bearer "):
        token = token.split(" ", 1)[1].strip()
    
    resultado = validar_token(token)
    
    if not resultado.get("valido"):
        raise Exception("Unauthorized")
    
    # Retornar contexto con información del usuario
    return {
        "principalId": resultado["correo"],
        "policyDocument": {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Action": "execute-api:Invoke",
                    "Effect": "Allow",
                    "Resource": event["methodArn"]
                }
            ]
        },
        "context": {
            "correo": resultado["correo"],
            "role": resultado["role"],
            "nombre": resultado["nombre"]
        }
    }