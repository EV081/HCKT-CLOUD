import json
import os
import time
from datetime import datetime, timezone

import boto3

from handlers.utils import validar_token

dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table(os.environ["TABLE_CONEXIONES"])
ttl_hours = int(os.getenv("CONNECTION_TTL_HOURS", "4"))

def lambda_handler(event, context):
    params = event.get("queryStringParameters") or {}
    token = params.get("token") or ""
    resultado = validar_token(token)

    if not resultado.get("valido"):
        return {
            "statusCode": 401,
            "body": json.dumps({"message": resultado.get("error")})
        }

    connection_id = event["requestContext"]["connectionId"]
    ahora = datetime.now(timezone.utc)

    item = {
        "conexion_id": connection_id,
        "usuario_correo": resultado["correo"],
        "rol": resultado.get("rol"),
        "created_at": ahora.isoformat(),
        "expiracion_ttl": int(time.time()) + ttl_hours * 3600
    }

    table.put_item(Item=item)

    return {
        "statusCode": 200,
        "body": json.dumps({"message": "Conexión aceptada"})
    }
