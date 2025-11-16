import json
import os

import boto3
from botocore.exceptions import ClientError

dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table(os.environ["TABLE_CONEXIONES"])
management_api = boto3.client(
    "apigatewaymanagementapi",
    endpoint_url=os.environ["WEBSOCKET_API_ENDPOINT"].replace("wss://", "https://")
)

def _broadcast(conexiones, payload):
    eliminados = []
    for conn in conexiones:
        connection_id = conn["conexion_id"]
        try:
            management_api.post_to_connection(
                ConnectionId=connection_id,
                Data=json.dumps(payload).encode("utf-8")
            )
        except ClientError as exc:
            status = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
            if status == 410:
                eliminados.append(connection_id)
            else:
                raise
    for connection_id in eliminados:
        table.delete_item(Key={"conexion_id": connection_id})

def lambda_handler(event, context):
    body = json.loads(event.get("body") or "{}")
    incidente_id = body.get("incidente_id")
    estado = body.get("estado")
    destinatarios = body.get("destinatarios")
    payload_extra = body.get("datos", {})

    if not incidente_id or not estado:
        return {
            "statusCode": 400,
            "body": json.dumps({"message": "incidente_id y estado son obligatorios"})
        }

    scan_kwargs = {}
    if destinatarios and isinstance(destinatarios, list):
        scan_kwargs["FilterExpression"] = "usuario_correo IN ({})".format(
            ", ".join([f":correo{i}" for i, _ in enumerate(destinatarios)])
        )
        scan_kwargs["ExpressionAttributeValues"] = {
            f":correo{i}": correo for i, correo in enumerate(destinatarios)
        }

    conexiones = []
    response = table.scan(**scan_kwargs)
    conexiones.extend(response.get("Items", []))
    while "LastEvaluatedKey" in response:
        scan_kwargs["ExclusiveStartKey"] = response["LastEvaluatedKey"]
        response = table.scan(**scan_kwargs)
        conexiones.extend(response.get("Items", []))

    if not conexiones:
        return {
            "statusCode": 200,
            "body": json.dumps({"message": "Sin conexiones activas"})
        }

    payload = {
        "type": "incident.update",
        "incidente_id": incidente_id,
        "estado": estado,
        "datos": payload_extra
    }

    _broadcast(conexiones, payload)

    return {
        "statusCode": 200,
        "body": json.dumps({"message": "Notificaciones enviadas", "destinatarios": len(conexiones)})
    }
