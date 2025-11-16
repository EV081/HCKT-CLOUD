import os
import json
import math
import boto3
from boto3.dynamodb.conditions import Attr
from utils import validar_token
from decimal import Decimal

TABLE_LOGS = os.environ.get("TABLE_LOGS")
CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*"
}

def _convert_decimals(obj):
    """
    Convierte recursivamente Decimal -> int/float para que sea JSON serializable
    y los números sigan siendo números en el JSON.
    """
    if isinstance(obj, list):
        return [_convert_decimals(x) for x in obj]
    if isinstance(obj, dict):
        return {k: _convert_decimals(v) for k, v in obj.items()}
    if isinstance(obj, Decimal):
        if obj % 1 == 0:
            return int(obj)
        return float(obj)
    return obj

def _resp(code, body):
    safe_body = _convert_decimals(body)
    return {
        "statusCode": code,
        "headers": CORS_HEADERS,
        "body": json.dumps(safe_body, ensure_ascii=False)
    }

def _safe_int(v, default):
    try:
        return int(v)
    except Exception:
        return default

def lambda_handler(event, context):
    headers = event.get("headers") or {}
    auth_header = headers.get("Authorization") or headers.get("authorization") or ""
    if auth_header.lower().startswith("bearer "):
        auth_header = auth_header.split(" ", 1)[1].strip()
    token = auth_header

    resultado_validacion = validar_token(token)

    if not resultado_validacion.get("valido"):
        return _resp(401, {"error": resultado_validacion.get("error")})

    usuario_autenticado = {
        "correo": resultado_validacion.get("correo"),
        "rol": resultado_validacion.get("rol")
    }

    rol = usuario_autenticado["rol"]

    if rol not in ["personal_administrativo", "autoridad"]:
        return _resp(403, {"error": "No tienes permisos para listar logs"})

    body = json.loads(event.get("body") or "{}")
    page = _safe_int(body.get("page", 0), 0)
    size = _safe_int(body.get("size", body.get("limit", 10)), 10)

    if size <= 0 or size > 100:
        size = 10
    if page < 0:
        page = 0

    ddb = boto3.resource("dynamodb")
    table = ddb.Table(TABLE_LOGS)

    filter_expr = None

    total = 0
    count_args = {
        "Select": "COUNT"
    }
    if filter_expr is not None:
        count_args["FilterExpression"] = filter_expr

    lek = None
    while True:
        if lek:
            count_args["ExclusiveStartKey"] = lek
        rcount = table.scan(**count_args)
        total += rcount.get("Count", 0)
        lek = rcount.get("LastEvaluatedKey")
        if not lek:
            break

    total_pages = math.ceil(total / size) if size > 0 else 0

    if total_pages and page >= total_pages:
        return _resp(200, {
            "contents": [],
            "page": page,
            "size": size,
            "totalElements": total,
            "totalPages": total_pages
        })

    qargs = {
        "Limit": size
    }
    if filter_expr is not None:
        qargs["FilterExpression"] = filter_expr

    lek = None
    for _ in range(page):
        if lek:
            qargs["ExclusiveStartKey"] = lek
        rskip = table.scan(**qargs)
        lek = rskip.get("LastEvaluatedKey")
        if not lek:
            return _resp(200, {
                "contents": [],
                "page": page,
                "size": size,
                "totalElements": total,
                "totalPages": total_pages
            })

    if lek:
        qargs["ExclusiveStartKey"] = lek
    rpage = table.scan(**qargs)
    items = rpage.get("Items", [])

    return _resp(200, {
        "contents": items,
        "page": page,
        "size": size,
        "totalElements": total,
        "totalPages": total_pages
    })
