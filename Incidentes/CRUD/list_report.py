import os
import json
import math
import boto3
from boto3.dynamodb.conditions import Attr
from CRUD.utils import validar_token
from decimal import Decimal

TABLE_INCIDENTES = os.environ.get("TABLE_INCIDENTES")
CORS_HEADERS = {"Access-Control-Allow-Origin": "*"}

dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table(TABLE_INCIDENTES)


def _convert_decimals(obj):
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
        "body": json.dumps(safe_body, ensure_ascii=False),
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
        "rol": resultado_validacion.get("rol"),
    }

    rol = usuario_autenticado["rol"]

    if rol not in ["estudiante", "personal_administrativo", "autoridad"]:
        return _resp(403, {"error": "No tienes permisos para listar incidentes"})

    body = json.loads(event.get("body") or "{}")
    page = _safe_int(body.get("page", 0), 0)
    size = _safe_int(body.get("size", body.get("limit", 10)), 10)

    if size <= 0 or size > 100:
        size = 10
    if page < 0:
        page = 0

    filtro_tipo = body.get("tipo")
    filtro_nivel = body.get("nivel_urgencia")
    filtro_estado = body.get("estado")

    filter_expr = None
    if filtro_tipo:
        cond = Attr("tipo").eq(filtro_tipo)
        filter_expr = cond if filter_expr is None else (filter_expr & cond)
    if filtro_nivel:
        cond = Attr("nivel_urgencia").eq(filtro_nivel)
        filter_expr = cond if filter_expr is None else (filter_expr & cond)
    if filtro_estado:
        cond = Attr("estado").eq(filtro_estado)
        filter_expr = cond if filter_expr is None else (filter_expr & cond)

    total = 0
    count_args = {"Select": "COUNT"}
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
            "totalPages": total_pages,
        })

    qargs = {"Limit": size}
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
                "totalPages": total_pages,
            })

    if lek:
        qargs["ExclusiveStartKey"] = lek
    rpage = table.scan(**qargs)
    items = rpage.get("Items", [])

    if rol == "estudiante":
        items = [
            {
                "titulo": item.get("titulo"),
                "piso": item.get("piso"),
                "tipo": item.get("tipo"),
                "nivel_urgencia": item.get("nivel_urgencia"),
                "estado": item.get("estado"),
                "created_at": item.get("created_at"),
                "updated_at": item.get("updated_at"),
            }
            for item in items
        ]
    else:
        items = [
            {
                "incidente_id": item.get("incidente_id"),
                "titulo": item.get("titulo"),
                "descripcion": item.get("descripcion"),
                "piso": item.get("piso"),
                "ubicacion": item.get("ubicacion"),
                "tipo": item.get("tipo"),
                "nivel_urgencia": item.get("nivel_urgencia"),
                "evidencias": item.get("evidencias", []),
                "estado": item.get("estado"),
                "usuario_correo": item.get("usuario_correo"),
                "created_at": item.get("created_at"),
                "updated_at": item.get("updated_at"),
                "coordenadas": item.get("coordenadas"),
            }
            for item in items
        ]

    return _resp(200, {
        "contents": items,
        "page": page,
        "size": size,
        "totalElements": total,
        "totalPages": total_pages,
    })
