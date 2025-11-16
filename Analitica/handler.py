"""
Handler para el microservicio de Analítica - ETL simplificado con Lambda
"""

import json
import os
import time
from datetime import datetime
from decimal import Decimal
import boto3
from pathlib import Path

S3_PREFIX = "analitica/ingesta"


def _decimal_default(obj):
    """Convierte Decimal a tipo serializable JSON"""
    if isinstance(obj, Decimal):
        return float(obj) if obj % 1 else int(obj)
    raise TypeError(f"No serializable type: {type(obj)}")


def _parse_table_mapping(raw_value: str):
    """Parsea ANALITICA_TABLES desde .env"""
    mapping = {}
    for pair in raw_value.split(","):
        if "=" not in pair:
            continue
        logical, physical = pair.split("=", 1)
        logical = logical.strip()
        physical = physical.strip()
        if logical and physical:
            mapping[logical] = physical
    return mapping


def etl_dynamodb_to_s3(event, context):
    """
    ETL: Exporta todas las tablas de DynamoDB a S3
    """
    try:
        # Configuración
        tables_raw = os.environ.get("ANALITICA_TABLES")
        if not tables_raw:
            raise ValueError("ANALITICA_TABLES no está definido")

        tables = _parse_table_mapping(tables_raw)
        bucket = os.environ["ANALITICA_S3_BUCKET"]
        region = os.environ.get("AWS_REGION", "us-east-1")

        dynamodb = boto3.resource("dynamodb", region_name=region)
        s3 = boto3.client("s3", region_name=region)
        timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")

        results = []

        # Exportar cada tabla
        for logical_name, table_name in tables.items():
            print(f"📊 Exportando {table_name} como {logical_name}...")

            table = dynamodb.Table(table_name)
            items = []
            last_evaluated_key = None

            # Paginación: leer toda la tabla
            while True:
                response = table.scan(
                    ExclusiveStartKey=last_evaluated_key
                ) if last_evaluated_key else table.scan()

                items.extend(response.get("Items", []))
                last_evaluated_key = response.get("LastEvaluatedKey")

                if not last_evaluated_key:
                    break
                time.sleep(1)  # Evitar throttling

            # Guardar en S3
            if items:
                file_name = f"{S3_PREFIX}/{logical_name}/{timestamp}_{logical_name}.json"
                s3.put_object(
                    Bucket=bucket,
                    Key=file_name,
                    Body=json.dumps(items, default=_decimal_default).encode("utf-8"),
                    ContentType="application/json",
                )
                results.append({
                    "table": logical_name,
                    "s3_path": f"s3://{bucket}/{file_name}",
                    "row_count": len(items),
                })

        return {
            "statusCode": 200,
            "body": json.dumps({
                "message": "Exportación completada",
                "results": results,
            }),
        }

    except Exception as e:
        print(f"Error en ETL: {e}")
        return {
            "statusCode": 500,
            "body": json.dumps({
                "error": str(e),
            }),
        }


# ------------------- Consultas Athena ------------------- #

# Clientes AWS
athena_client = boto3.client('athena')
s3_client = boto3.client('s3')
ecs_client = boto3.client('ecs')

# Configuración
ANALITICA_S3_BUCKET = os.environ.get('ANALITICA_S3_BUCKET', 'alerta-utec-analitica')
ANALITICA_GLUE_DATABASE = os.environ.get('ANALITICA_GLUE_DATABASE', 'alerta_utec_analitica')
ATHENA_OUTPUT_LOCATION = f"s3://{ANALITICA_S3_BUCKET}/athena-results/"


def _ejecutar_query_athena(query: str, descripcion: str = "Consulta"):
    """
    Ejecuta una consulta en Athena y retorna los resultados
    """
    try:
        print(f"📊 Ejecutando query: {descripcion}")
        
        # Iniciar ejecución de query
        response = athena_client.start_query_execution(
            QueryString=query,
            QueryExecutionContext={'Database': ANALITICA_GLUE_DATABASE},
            ResultConfiguration={'OutputLocation': ATHENA_OUTPUT_LOCATION}
        )
        
        query_execution_id = response['QueryExecutionId']
        print(f"🔍 Query ID: {query_execution_id}")
        
        # Esperar a que complete (máximo 30 segundos)
        max_attempts = 30
        attempt = 0
        
        while attempt < max_attempts:
            query_status = athena_client.get_query_execution(
                QueryExecutionId=query_execution_id
            )
            
            status = query_status['QueryExecution']['Status']['State']
            
            if status == 'SUCCEEDED':
                print(f"✅ Query completada exitosamente")
                break
            elif status in ['FAILED', 'CANCELLED']:
                error_msg = query_status['QueryExecution']['Status'].get('StateChangeReason', 'Unknown error')
                print(f"❌ Query falló: {error_msg}")
                return {
                    'success': False,
                    'error': error_msg
                }
            
            time.sleep(1)
            attempt += 1
        
        if attempt >= max_attempts:
            return {
                'success': False,
                'error': 'Timeout esperando resultados de la query'
            }
        
        # Obtener resultados
        results = athena_client.get_query_results(
            QueryExecutionId=query_execution_id
        )
        
        # Parsear resultados
        rows = results['ResultSet']['Rows']
        
        if len(rows) == 0:
            return {
                'success': True,
                'data': [],
                'columns': []
            }
        
        # Primera fila son los headers
        columns = [col['VarCharValue'] for col in rows[0]['Data']]
        
        # Resto son los datos
        data = []
        for row in rows[1:]:
            row_data = {}
            for i, col in enumerate(row['Data']):
                row_data[columns[i]] = col.get('VarCharValue', None)
            data.append(row_data)
        
        print(f"📈 Resultados: {len(data)} filas")
        
        return {
            'success': True,
            'data': data,
            'columns': columns,
            'row_count': len(data)
        }
        
    except Exception as e:
        print(f"❌ Error ejecutando query: {e}")
        return {
            'success': False,
            'error': str(e)
        }


def analisis_incidentes_por_piso(event, context):
    """
    Lambda 1: Análisis de incidentes por piso y estado
    """
    query = """
    SELECT 
        piso,
        estado,
        COUNT(*) as total_incidentes
    FROM incidentes
    GROUP BY piso, estado
    ORDER BY piso, estado
    """
    
    resultado = _ejecutar_query_athena(query, "Incidentes por piso y estado")
    
    if not resultado['success']:
        return {
            'statusCode': 500,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({
                'error': resultado['error']
            })
        }
    
    return {
        'statusCode': 200,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*'
        },
        'body': json.dumps({
            'descripcion': 'Análisis de incidentes por piso y estado',
            'resultados': resultado['data'],
            'total_filas': resultado['row_count']
        })
    }


def analisis_incidentes_por_tipo(event, context):
    """
    Lambda 2: Análisis de incidentes por tipo y nivel de urgencia
    """
    query = """
    SELECT 
        tipo,
        nivel_urgencia,
        COUNT(*) as cantidad,
        ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER(), 2) as porcentaje
    FROM incidentes
    GROUP BY tipo, nivel_urgencia
    ORDER BY tipo, nivel_urgencia
    """
    
    resultado = _ejecutar_query_athena(query, "Incidentes por tipo y urgencia")
    
    if not resultado['success']:
        return {
            'statusCode': 500,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({
                'error': resultado['error']
            })
        }
    
    return {
        'statusCode': 200,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*'
        },
        'body': json.dumps({
            'descripcion': 'Distribución de incidentes por tipo y nivel de urgencia',
            'resultados': resultado['data'],
            'total_filas': resultado['row_count']
        })
    }


def analisis_tiempo_resolucion(event, context):
    """
    Lambda 3: Análisis de tiempo de resolución de incidentes
    """
    query = """
    SELECT 
        incidente_id,
        titulo,
        tipo,
        nivel_urgencia,
        creado_en,
        actualizado_en,
        estado,
        CASE 
            WHEN actualizado_en IS NOT NULL AND estado = 'resuelto' 
            THEN date_diff('hour', 
                          from_iso8601_timestamp(creado_en), 
                          from_iso8601_timestamp(actualizado_en))
            ELSE NULL 
        END as horas_resolucion
    FROM incidentes
    WHERE estado = 'resuelto'
    ORDER BY horas_resolucion
    """
    
    resultado = _ejecutar_query_athena(query, "Tiempo de resolución")
    
    if not resultado['success']:
        return {
            'statusCode': 500,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({
                'error': resultado['error']
            })
        }
    
    return {
        'statusCode': 200,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*'
        },
        'body': json.dumps({
            'descripcion': 'Análisis de tiempo de resolución de incidentes',
            'resultados': resultado['data'],
            'total_filas': resultado['row_count']
        })
    }


def analisis_reportes_por_usuario(event, context):
    """
    Lambda 4: Análisis de reportes por usuario estudiante
    """
    query = """
    SELECT 
        i.usuario_correo,
        u.nombre,
        u.rol,
        COUNT(*) as total_reportes,
        SUM(CASE WHEN i.estado = 'resuelto' THEN 1 ELSE 0 END) as reportes_resueltos,
        SUM(CASE WHEN i.estado = 'en_progreso' THEN 1 ELSE 0 END) as reportes_en_progreso,
        SUM(CASE WHEN i.estado = 'reportado' THEN 1 ELSE 0 END) as reportes_pendientes
    FROM incidentes i
    LEFT JOIN usuarios u ON i.usuario_correo = u.correo
    WHERE u.rol = 'estudiante' OR u.rol IS NULL
    GROUP BY i.usuario_correo, u.nombre, u.rol
    ORDER BY total_reportes DESC
    LIMIT 20
    """
    
    resultado = _ejecutar_query_athena(query, "Reportes por usuario")
    
    if not resultado['success']:
        return {
            'statusCode': 500,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({
                'error': resultado['error']
            })
        }
    
    return {
        'statusCode': 200,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*'
        },
        'body': json.dumps({
            'descripcion': 'Top 20 usuarios estudiantes por cantidad de reportes',
            'resultados': resultado['data'],
            'total_filas': resultado['row_count']
        })
    }


def trigger_etl_pipeline(event, context):
    """
    Lambda 5: Triggerea el DAG de Airflow manualmente actualizando el servicio ECS
    """
    try:
        cluster = 'alerta-utec-analitica-cluster'
        service = 'alerta-utec-analitica-airflow'
        
        print(f"🚀 Triggeando ETL Pipeline en Airflow...")
        print(f"   Cluster: {cluster}")
        print(f"   Service: {service}")
        
        # Forzar nuevo despliegue para actualizar el DAG
        response = ecs_client.update_service(
            cluster=cluster,
            service=service,
            forceNewDeployment=True
        )
        
        service_arn = response['service']['serviceArn']
        status = response['service']['status']
        
        print(f"✅ Servicio actualizado: {status}")
        
        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({
                'message': 'ETL Pipeline triggerado exitosamente',
                'cluster': cluster,
                'service': service,
                'status': status,
                'instrucciones': [
                    'El servicio de Airflow se está reiniciando',
                    'Espera 2-3 minutos para que el DAG esté disponible',
                    'Accede a la interfaz de Airflow y activa el DAG manualmente',
                    'O espera a que se ejecute según el schedule (@daily)'
                ]
            })
        }
        
    except Exception as e:
        print(f"❌ Error triggeando ETL: {e}")
        return {
            'statusCode': 500,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({
                'error': str(e),
                'message': 'Error al triggear el ETL Pipeline'
            })
        }


def upload_dag(event, context):
    """
    Sube el archivo etl_dynamodb.py al bucket S3 de analítica
    """
    try:
        s3 = boto3.client('s3')
        bucket = os.environ['ANALITICA_S3_BUCKET']
        
        # Leer el archivo DAG
        dag_path = Path(__file__).parent / 'etl_dynamodb.py'
        
        if not dag_path.exists():
            return {
                'statusCode': 404,
                'body': json.dumps({
                    'error': f'Archivo DAG no encontrado: {dag_path}'
                })
            }
        
        with open(dag_path, 'r', encoding='utf-8') as f:
            dag_content = f.read()
        
        # Subir a S3
        s3.put_object(
            Bucket=bucket,
            Key='dags/etl_dynamodb.py',
            Body=dag_content.encode('utf-8'),
            ContentType='text/x-python'
        )
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': 'DAG subido exitosamente a S3',
                'bucket': bucket,
                'key': 'dags/etl_dynamodb.py'
            })
        }
    
    except Exception as e:
        print(f"Error subiendo DAG: {e}")
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': str(e)
            })
        }
