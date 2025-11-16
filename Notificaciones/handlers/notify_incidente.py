import json
import os
from datetime import datetime

import boto3
from botocore.exceptions import ClientError
from boto3.dynamodb.conditions import Attr

dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table(os.environ["TABLE_CONEXIONES"])
management_api = boto3.client(
    "apigatewaymanagementapi",
    endpoint_url=os.environ["WEBSOCKET_API_ENDPOINT"].replace("wss://", "https://")
)

def _broadcast(conexiones, payload):
    eliminados = []
    enviados = 0
    for conn in conexiones:
        connection_id = conn["conexion_id"]
        try:
            management_api.post_to_connection(
                ConnectionId=connection_id,
                Data=json.dumps(payload, ensure_ascii=False).encode("utf-8")
            )
            enviados += 1
            print(f"✓ Enviado a {conn.get('usuario_correo')} ({connection_id})")
        except ClientError as exc:
            status = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
            if status == 410:
                eliminados.append(connection_id)
                print(f"✗ Conexión obsoleta: {connection_id}")
            else:
                print(f"Error enviando a {connection_id}: {exc}")
    
    for connection_id in eliminados:
        try:
            table.delete_item(Key={"conexion_id": connection_id})
        except Exception as e:
            print(f"Error eliminando conexión {connection_id}: {e}")
    
    return enviados

def lambda_handler(event, context):
    body = json.loads(event.get("body") or "{}")
    
    # Campos requeridos
    tipo = body.get("tipo")
    titulo = body.get("titulo")
    mensaje = body.get("mensaje")
    incidente_id = body.get("incidente_id")
    
    # Campos opcionales
    destinatarios = body.get("destinatarios")

    print(f"📨 Notificación recibida - Tipo: {tipo}, Incidente: {incidente_id}")
    print(f"📋 Título: {titulo}")
    print(f"👥 Destinatarios: {destinatarios if destinatarios else 'TODOS'}")

    if not tipo or not titulo or not mensaje or not incidente_id:
        return {
            "statusCode": 400,
            "body": json.dumps({
                "message": "tipo, titulo, mensaje e incidente_id son obligatorios"
            })
        }

    # Validar tipo
    tipos_validos = ["incidente_actualizado", "incidente_creado", "incidente_resuelto"]
    if tipo not in tipos_validos:
        return {
            "statusCode": 400,
            "body": json.dumps({
                "message": f"tipo debe ser uno de: {', '.join(tipos_validos)}"
            })
        }

    # Escanear conexiones
    scan_kwargs = {}
    if destinatarios and isinstance(destinatarios, list) and len(destinatarios) > 0:
        filter_expr = Attr("usuario_correo").is_in(destinatarios)
        scan_kwargs["FilterExpression"] = filter_expr
        print(f"🔍 Buscando conexiones para destinatarios específicos...")
    else:
        print(f"🔍 Buscando TODAS las conexiones activas...")

    conexiones = []
    try:
        response = table.scan(**scan_kwargs)
        conexiones.extend(response.get("Items", []))
        while "LastEvaluatedKey" in response:
            scan_kwargs["ExclusiveStartKey"] = response["LastEvaluatedKey"]
            response = table.scan(**scan_kwargs)
            conexiones.extend(response.get("Items", []))
        
        print(f"📊 Conexiones encontradas: {len(conexiones)}")
        for conn in conexiones:
            print(f"  - {conn.get('usuario_correo')} ({conn.get('rol')}) - ID: {conn.get('conexion_id')}")
            
    except Exception as e:
        print(f"❌ Error escaneando conexiones: {e}")
        return {
            "statusCode": 500,
            "body": json.dumps({"message": "Error al obtener conexiones", "error": str(e)})
        }

    if not conexiones:
        print("⚠️ No hay conexiones activas")
        return {
            "statusCode": 200,
            "body": json.dumps({"message": "Sin conexiones activas"})
        }

    # Construir payload de notificación
    payload = {
        "tipo": tipo,
        "titulo": titulo,
        "mensaje": mensaje,
        "incidente_id": incidente_id,
        "timestamp": datetime.utcnow().isoformat() + "Z"
    }

    print(f"📤 Enviando notificaciones...")
    enviados = _broadcast(conexiones, payload)

    return {
        "statusCode": 200,
        "body": json.dumps({
            "message": "Notificaciones enviadas",
            "conexiones_encontradas": len(conexiones),
            "mensajes_enviados": enviados
        })
    }
