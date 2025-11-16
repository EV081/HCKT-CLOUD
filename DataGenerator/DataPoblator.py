import json
import boto3
import os
from dotenv import load_dotenv
from botocore.exceptions import ClientError
import time
from decimal import Decimal
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
import random as random_module

# Cargar variables de entorno
load_dotenv()

# Configuración de AWS
AWS_REGION = os.getenv('AWS_REGION', 'us-east-1')

dynamodb = boto3.resource('dynamodb', region_name=AWS_REGION)
dynamodb_client = boto3.client('dynamodb', region_name=AWS_REGION)

# Nombres de las tablas
TABLE_USUARIOS = os.getenv('TABLE_USUARIOS')
TABLE_INCIDENTES = os.getenv('TABLE_INCIDENTES')
TABLE_EMPLEADOS = os.getenv('TABLE_EMPLEADOS')
TABLE_LOGS = os.getenv('TABLE_LOGS')
TABLE_CONEXIONES = os.getenv('TABLE_CONEXIONES')

# Carpeta con los datos JSON
DATA_DIR = "example-data"

# Mapeo de archivos JSON a tablas
TABLE_MAPPING = {
    "usuarios.json": {
        "table_name": TABLE_USUARIOS,
        "pk": "usuario_id",
        "sk": None
    },
    "incidentes.json": {
        "table_name": TABLE_INCIDENTES,
        "pk": "incidente_id",
        "sk": None
    },
    "empleados.json": {
        "table_name": TABLE_EMPLEADOS,
        "pk": "empleado_id",
        "sk": None
    },
    "logs.json": {
        "table_name": TABLE_LOGS,
        "pk": "registro_id",
        "sk": None
    },
    "conexiones.json": {
        "table_name": TABLE_CONEXIONES,
        "pk": "conexion_id",
        "sk": None
    }
}


def convert_float_to_decimal(obj):
    """Convierte float a Decimal recursivamente"""
    if isinstance(obj, list):
        return [convert_float_to_decimal(item) for item in obj]
    elif isinstance(obj, dict):
        return {key: convert_float_to_decimal(value) for key, value in obj.items()}
    elif isinstance(obj, float):
        return Decimal(str(obj))
    else:
        return obj


def table_exists(table_name):
    """Verifica si una tabla existe"""
    try:
        dynamodb_client.describe_table(TableName=table_name)
        return True
    except ClientError as e:
        if e.response['Error']['Code'] == 'ResourceNotFoundException':
            return False
        else:
            raise


def load_json_file(filename):
    """Carga un archivo JSON"""
    filepath = os.path.join(DATA_DIR, filename)
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return convert_float_to_decimal(data)
    except FileNotFoundError:
        print(f"⚠️  Archivo no encontrado: {filepath}")
        return None
    except json.JSONDecodeError as e:
        print(f"⚠️  Error al decodificar JSON en {filename}: {e}")
        return None


def delete_all_items_from_table(table_name, pk_name, sk_name=None):
    """Elimina todos los items de una tabla"""
    try:
        table = dynamodb.Table(table_name)
        
        print(f"   🗑️  Escaneando items en '{table_name}'...")
        response = table.scan()
        items = response.get('Items', [])
        
        while 'LastEvaluatedKey' in response:
            response = table.scan(ExclusiveStartKey=response['LastEvaluatedKey'])
            items.extend(response.get('Items', []))
        
        if not items:
            print(f"   ℹ️  La tabla '{table_name}' ya está vacía")
            return True
        
        print(f"   🗑️  Eliminando {len(items)} items de '{table_name}'...")
        
        with table.batch_writer() as batch:
            for item in items:
                key = {pk_name: item[pk_name]}
                if sk_name:
                    key[sk_name] = item[sk_name]
                batch.delete_item(Key=key)
        
        print(f"   ✅ {len(items)} items eliminados")
        return True
        
    except Exception as e:
        print(f"   ❌ Error al limpiar tabla: {str(e)}")
        return False


def batch_write_items(table, items, table_name):
    """Escribe items en lotes con retry"""
    success_count = 0
    error_count = 0
    total_items = len(items)
    batch_size = 25
    count_lock = Lock()
    
    batches = [items[i:i + batch_size] for i in range(0, total_items, batch_size)]
    
    def process_batch_with_retry(batch, max_retries=5):
        local_success = 0
        local_errors = 0
        
        for attempt in range(max_retries):
            try:
                with table.batch_writer() as batch_writer:
                    for item in batch:
                        try:
                            batch_writer.put_item(Item=item)
                            local_success += 1
                        except ClientError as e:
                            if e.response['Error']['Code'] == 'ProvisionedThroughputExceededException':
                                raise
                            else:
                                local_errors += 1
                
                return local_success, local_errors
                
            except ClientError as e:
                if e.response['Error']['Code'] == 'ProvisionedThroughputExceededException':
                    if attempt < max_retries - 1:
                        wait_time = (2 ** attempt) + random_module.uniform(0, 1)
                        time.sleep(wait_time)
                        local_success = 0
                        local_errors = 0
                        continue
                else:
                    local_errors += len(batch)
                    return 0, local_errors
        
        return local_success, local_errors
    
    try:
        num_threads = min(10, len(batches))
        
        with ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = {executor.submit(process_batch_with_retry, batch): batch for batch in batches}
            
            for future in as_completed(futures):
                try:
                    local_success, local_errors = future.result()
                    with count_lock:
                        success_count += local_success
                        error_count += local_errors
                        
                        if (success_count % 100 == 0) or (success_count + error_count >= total_items):
                            porcentaje = ((success_count + error_count) / total_items) * 100
                            print(f"      📊 Progreso: {success_count}/{total_items} ({porcentaje:.1f}%)")
                
                except Exception as e:
                    with count_lock:
                        error_count += len(futures[future])
    
    except Exception as e:
        print(f"   ❌ Error: {str(e)}")
        return success_count, total_items - success_count
    
    return success_count, error_count


def populate_table(filename, table_config):
    """Puebla una tabla"""
    table_name = table_config["table_name"]
    pk_name = table_config["pk"]
    sk_name = table_config["sk"]
    
    print(f"\n📤 Poblando tabla: {table_name}")
    print(f"   Archivo: {filename}")
    
    # Verificar que la tabla existe
    if not table_exists(table_name):
        print(f"   ⚠️  Tabla '{table_name}' no existe. Debe crearse primero con Serverless Framework")
        return False
    
    print(f"   ✅ Tabla '{table_name}' existe")
    
    # Limpiar datos existentes
    print(f"   🗑️  Limpiando datos existentes...")
    if not delete_all_items_from_table(table_name, pk_name, sk_name):
        print(f"   ❌ Error al limpiar la tabla")
        return False
    
    # Cargar datos
    items = load_json_file(filename)
    
    if items is None or not isinstance(items, list) or len(items) == 0:
        print(f"   ⚠️  No hay datos para insertar")
        return True
    
    print(f"   📊 Total de items: {len(items)}")
    
    try:
        table = dynamodb.Table(table_name)
        success_count, error_count = batch_write_items(table, items, table_name)
        
        print(f"   ✅ Insertados: {success_count} items")
        if error_count > 0:
            print(f"   ⚠️  Errores: {error_count} items")
        
        return error_count == 0
        
    except Exception as e:
        print(f"   ❌ Error: {str(e)}")
        return False


def verify_credentials():
    """Verifica credenciales AWS"""
    try:
        session = boto3.Session()
        credentials = session.get_credentials()
        
        if credentials is None:
            print("❌ No se encontraron credenciales de AWS")
            return False
        
        return True
    except Exception as e:
        print(f"❌ Error al verificar credenciales: {e}")
        return False


def main():
    """Función principal"""
    print("=" * 60)
    print("🚀 ALERTA UTEC - DATA POBLATOR")
    print("=" * 60)

    if not verify_credentials():
        return

    if not os.path.exists(DATA_DIR):
        print(f"\n❌ La carpeta '{DATA_DIR}/' no existe")
        return

    print(f"\n🔌 Conectando a DynamoDB ({AWS_REGION})")
    print("✅ Conexión establecida")

    print("\n" + "=" * 60)
    print("📊 POBLANDO TABLAS")
    print("=" * 60)

    results = {}
    for filename, config in TABLE_MAPPING.items():
        if config["table_name"]:
            success = populate_table(filename, config)
            results[filename] = success
        time.sleep(1)  # Pequeña pausa entre tablas

    print("\n" + "=" * 60)
    print("📋 RESUMEN")
    print("=" * 60)

    successful = sum(1 for success in results.values() if success)
    failed = len(results) - successful

    print(f"\n✅ Tablas pobladas: {successful}")
    if failed > 0:
        print(f"❌ Tablas con errores: {failed}")

    print("\n" + "=" * 60)
    print("🎉 COMPLETADO")
    print("=" * 60)


if __name__ == "__main__":
    main()
