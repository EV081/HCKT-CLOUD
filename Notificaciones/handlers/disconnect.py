import os

import boto3

dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table(os.environ["TABLE_CONEXIONES"])

def lambda_handler(event, context):
    connection_id = event["requestContext"]["connectionId"]
    table.delete_item(Key={"conexion_id": connection_id})
    return {"statusCode": 200, "body": "Desconectado"}
