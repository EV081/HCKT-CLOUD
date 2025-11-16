import os
import json
import math
import boto3
from boto3.dynamodb.conditions import Key

TABLE_INCIDENTES = os.environ.get("TABLE_INCIDENTES")

def _resp(code, body):
    return {"statusCode": code, "body": json.dumps(body, ensure_ascii=False, default=str)}

def _safe_int(v, default):
    try:
        return int(v)
    except Exception:
        return default

def lambda_handler(event, context):
    token = event.get("headers", {}).get("authorization", "").split(" ")[-1]
    
    resultado_validacion = validar_token(token)
    
    if not resultado_validacion.get("valido"):
        return _resp(401, {"error": resultado_validacion.get("error")})
    
    usuario_autenticado = {
        "correo": resultado_validacion.get("correo"),
        "role": resultado_validacion.get("role")
    }

    body = json.loads(event.get("body") or "{}")
    tenant_id = body.get("tenant_id")
    if not tenant_id:
        return _resp(400, {"error":"Falta tenant_id en el body"})

    page = _safe_int(body.get("page", 0), 0)
    size = _safe_int(body.get("size", body.get("limit", 10)), 10)
    if size <= 0 or size > 100:
        size = 10
    if page < 0:
        page = 0

    ddb = boto3.resource("dynamodb")
    table = ddb.Table(TABLE_INCIDENTES)

    total = 0
    count_args = {
        "KeyConditionExpression": Key("tenant_id").eq(tenant_id),
        "Select": "COUNT"
    }
    lek = None
    while True:
        if lek:
            count_args["ExclusiveStartKey"] = lek
        rcount = table.query(**count_args)
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
        "KeyConditionExpression": Key("tenant_id").eq(tenant_id),
        "Limit": size
    }

    lek = None
    for _ in range(page):
        if lek:
            qargs["ExclusiveStartKey"] = lek
        rskip = table.query(**qargs)
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
    rpage = table.query(**qargs)
    items = rpage.get("Items", [])

    if usuario_autenticado["role"] == "user":
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
    elif usuario_autenticado["role"] in ["admin", "operador"]:
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
