import os
import json
import math
import boto3
from boto3.dynamodb.conditions import Attr
from CRUD.utils import validar_token

TABLE_INCIDENTES = os.environ.get("TABLE_INCIDENTES")

def _resp(code, body):
    return {"statusCode": code, "body": json.dumps(body, ensure_ascii=False, default=str)}

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
    correo_usuario = usuario_autenticado["correo"]

    if rol not in ["estudiante", "personal_administrativo", "autoridad"]:
        return _resp(403, {"error": "No tienes permisos para listar incidentes"})

    body = json.loads(event.get("body") or "{}")
    page = _safe_int(body.get("page", 0), 0)
    size = _safe_int(body.get("size", body.get("limit", 10)), 10)

    if size <= 0 or size > 100:
        size = 10
    if page < 0:
        page = 0

    ddb = boto3.resource("dynamodb")
    table = ddb.Table(TABLE_INCIDENTES)

    filter_expr = None
    if rol == "estudiante":
        filter_expr = Attr("usuario_correo").eq(correo_usuario)

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

    if rol == "estudiante":
        items = [
            {
                "titulo": item.get("titulo"),
                "piso": item.get("piso"),
                "tipo": item.get("tipo"),
                "nivel_urgencia": item.get("nivel_urgencia"),
                "estado": item.get("estado"),
                "created_at": item.get("created_at"),
                "updated_at": item.get("updated_at")
            }
            for item in items
        ]
    elif rol in ["personal_administrativo", "autoridad"]:
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
                "updated_at": item.get("updated_at")
            }
            for item in items
        ]

    return _resp(200, {
        "contents": items,
        "page": page,
        "size": size,
        "totalElements": total,
        "totalPages": total_pages
    })
