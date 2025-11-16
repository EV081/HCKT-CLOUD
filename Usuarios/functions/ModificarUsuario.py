import boto3
import os
import json

TABLE_USUARIOS_NAME = os.getenv("TABLE_USUARIOS", "TABLE_USUARIOS")

dynamodb = boto3.resource("dynamodb")
usuarios_table = dynamodb.Table(TABLE_USUARIOS_NAME)

def _parse_body(event):
    body = event.get("body", {})
    if isinstance(body, str):
        body = json.loads(body) if body.strip() else {}
    elif not isinstance(body, dict):
        body = {}
    return body

def lambda_handler(event, context):
    body = _parse_body(event)
    
    # Obtener usuario autenticado del authorizer
    authorizer = event.get("requestContext", {}).get("authorizer", {})
    usuario_autenticado = {
        "correo": authorizer.get("correo"),
        "role": authorizer.get("role"),
        "usuario_id": authorizer.get("usuario_id")  # Aseguramos que el usuario_id esté disponible
    }

    usuario_id = body.get("usuario_id")
    if not usuario_id:
        return {
            "statusCode": 400,
            "body": json.dumps({"message": "usuario_id es obligatorio"})
        }

    # Verificar permisos: solo el usuario autenticado puede modificar su propio perfil
    es_mismo_usuario = usuario_autenticado["usuario_id"] == usuario_id
    
    if not es_mismo_usuario:
        return {
            "statusCode": 403,
            "body": json.dumps({"message": "Solo puedes modificar tu propio perfil"})
        }

    # Obtener la información del usuario a actualizar
    resp = usuarios_table.get_item(Key={"usuario_id": usuario_id})
    if "Item" not in resp:
        return {
            "statusCode": 404,
            "body": json.dumps({"message": "Usuario no encontrado"})
        }

    update_expr = "SET "
    expr_attr_values = {}
    expr_attr_names = {}
    updates = []

    # Campos permitidos para actualizar
    if "nombre" in body:
        updates.append("#nombre = :nombre")
        expr_attr_names["#nombre"] = "nombre"
        expr_attr_values[":nombre"] = body["nombre"]

    if "contrasena" in body:
        if len(body["contrasena"]) < 6:
            return {
                "statusCode": 400,
                "body": json.dumps({"message": "La contraseña debe tener al menos 6 caracteres"})
            }
        updates.append("contrasena = :contrasena")
        expr_attr_values[":contrasena"] = body["contrasena"]

    # Si no hay cambios, devolver error
    if not updates:
        return {
            "statusCode": 400,
            "body": json.dumps({"message": "No hay campos para actualizar"})
        }

    update_expr += ", ".join(updates)

    kwargs = {
        "Key": {"usuario_id": usuario_id},
        "UpdateExpression": update_expr,
        "ExpressionAttributeValues": expr_attr_values,
        "ReturnValues": "ALL_NEW"
    }
    
    if expr_attr_names:
        kwargs["ExpressionAttributeNames"] = expr_attr_names

    try:
        updated_item = usuarios_table.update_item(**kwargs)
        return {
            "statusCode": 200,
            "body": json.dumps({
                "message": "Usuario actualizado correctamente",
                "usuario": updated_item["Attributes"]
            })
        }
    except Exception as e:
        return {
            "statusCode": 500,
            "body": json.dumps({"message": f"Error al actualizar usuario: {str(e)}"})
        }
