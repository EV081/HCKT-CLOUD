import json
import os
import time
from datetime import datetime
from decimal import Decimal

import boto3
from airflow import DAG
from airflow.decorators import task

DEFAULT_ARGS = {
    "owner": "analitica",
    "retries": 1,
}

S3_PREFIX = "analitica/ingesta"

def _decimal_default(obj):
    if isinstance(obj, Decimal):
        return float(obj) if obj % 1 else int(obj)
    raise TypeError(f"No serializable type: {type(obj)}")

def _parse_table_mapping(raw_value: str):
    mapping = {}
    for pair in raw_value.split(","):
        if "=" not in pair:
            continue
        logical, physical = pair.split("=", 1)
        logical = logical.strip()
        physical = physical.strip()
        if logical and physical:
            mapping[logical] = physical
    if not mapping:
        raise ValueError("ANALITICA_TABLES no contiene pares válidos clave=tabla")
    return mapping

with DAG(
    dag_id="etl_dynamodb_a_glue_athena",
    description="Ingesta de DynamoDB a S3 con Glue y Athena",
    schedule_interval="@daily",
    start_date=datetime.now(),  # Comenzar desde ahora, no desde el pasado
    catchup=False,
    default_args=DEFAULT_ARGS,
    tags=["analitica", "ingesta"],
    is_paused_upon_creation=True,  # Pausado al crearse, activar manualmente
) as dag:

    @task()
    def load_config():
        tables_raw = os.environ.get("ANALITICA_TABLES")
        if not tables_raw:
            raise ValueError("Definir ANALITICA_TABLES en el entorno (formato clave=tabla,...).")
        account_id = os.environ.get("AWS_ACCOUNT_ID")
        if not account_id:
            raise ValueError("AWS_ACCOUNT_ID no está definido en el entorno.")
        
        # Rol hardcodeado como LabRole
        glue_role_arn = f"arn:aws:iam::{account_id}:role/LabRole"
        
        config = {
            "tables": _parse_table_mapping(tables_raw),
            "bucket": os.environ["ANALITICA_S3_BUCKET"],
            "prefix": S3_PREFIX,
            "glue_database": os.environ["ANALITICA_GLUE_DATABASE"],
            "glue_crawler": os.environ["ANALITICA_GLUE_CRAWLER"],
            "glue_role": glue_role_arn,
            "region": os.environ.get("AWS_REGION", "us-east-1"),
        }
        return config

    @task()
    def ensure_bucket(cfg):
        s3 = boto3.client("s3", region_name=cfg["region"])
        bucket = cfg["bucket"]
        try:
            s3.head_bucket(Bucket=bucket)
        except Exception:
            create_args = {"Bucket": bucket}
            if cfg["region"] != "us-east-1":
                create_args["CreateBucketConfiguration"] = {"LocationConstraint": cfg["region"]}
            s3.create_bucket(**create_args)
        return bucket

    @task()
    def export_tables(cfg):
        dynamodb = boto3.resource("dynamodb", region_name=cfg["region"])
        s3 = boto3.client("s3", region_name=cfg["region"])
        timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
        results = []

        print(f"📊 Iniciando exportación con timestamp: {timestamp}")
        print(f"🪣 Bucket destino: {cfg['bucket']}")
        print(f"📁 Prefijo: {cfg['prefix']}")

        for logical_name, table_name in cfg["tables"].items():
            print(f"\n📋 Procesando tabla: {table_name} (como {logical_name})")
            
            table = dynamodb.Table(table_name)
            items = []
            last_evaluated_key = None

            # Escanear todos los items
            while True:
                scan_kwargs = {}
                if last_evaluated_key:
                    scan_kwargs["ExclusiveStartKey"] = last_evaluated_key
                response = table.scan(**scan_kwargs)
                items.extend(response.get("Items", []))
                last_evaluated_key = response.get("LastEvaluatedKey")
                if not last_evaluated_key:
                    break

            print(f"  ✓ Total de registros: {len(items)}")

            # Formato JSON Lines
            jsonl_lines = []
            for item in items:
                json_line = json.dumps(item, default=_decimal_default, ensure_ascii=False)
                jsonl_lines.append(json_line)
            
            body = "\n".join(jsonl_lines)

            # 1. Guardar versión con timestamp (histórico)
            key_timestamped = f"{cfg['prefix']}/history/{logical_name}/{timestamp}/{logical_name}.jsonl"
            print(f"  📤 Subiendo versión histórica: {key_timestamped}")
            s3.put_object(
                Bucket=cfg["bucket"],
                Key=key_timestamped,
                Body=body.encode("utf-8"),
                ContentType="application/x-ndjson",
                Metadata={
                    "timestamp": timestamp,
                    "table": table_name,
                    "records": str(len(items))
                }
            )

            # 2. Guardar versión "latest" (usado por Athena/Glue)
            key_latest = f"{cfg['prefix']}/{logical_name}/{logical_name}.jsonl"
            print(f"  📤 Actualizando versión latest: {key_latest}")
            s3.put_object(
                Bucket=cfg["bucket"],
                Key=key_latest,
                Body=body.encode("utf-8"),
                ContentType="application/x-ndjson",
                Metadata={
                    "timestamp": timestamp,
                    "table": table_name,
                    "records": str(len(items))
                }
            )

            print(f"  ✅ Tabla {logical_name} exportada: {len(items)} registros")

            results.append({
                "logical": logical_name,
                "table": table_name,
                "records": len(items),
                "s3_key_latest": key_latest,
                "s3_key_history": key_timestamped
            })

        print(f"\n📊 Resumen de exportación ({timestamp}):")
        for r in results:
            print(f"  ✅ {r['logical']}: {r['records']} registros")
            print(f"     Latest: {r['s3_key_latest']}")
            print(f"     History: {r['s3_key_history']}")

        return {"timestamp": timestamp, "exports": results}

    @task()
    def ensure_glue_database(cfg):
        glue = boto3.client("glue", region_name=cfg["region"])
        try:
            glue.get_database(Name=cfg["glue_database"])
        except glue.exceptions.EntityNotFoundException:
            glue.create_database(
                DatabaseInput={
                    "Name": cfg["glue_database"],
                    "Description": "Datos ingeridos desde DynamoDB para analítica.",
                }
            )
        return cfg["glue_database"]

    @task()
    def ensure_glue_crawler(cfg):
        glue = boto3.client("glue", region_name=cfg["region"])
        s3_target = f"s3://{cfg['bucket']}/{cfg['prefix']}"
        crawler_name = cfg["glue_crawler"]
        crawler_args = {
            "Name": crawler_name,
            "Role": cfg["glue_role"],
            "DatabaseName": cfg["glue_database"],
            "Targets": {"S3Targets": [{"Path": s3_target}]},
            "Description": "Crawler para datos ingeridos desde DynamoDB.",
        }
        try:
            glue.get_crawler(Name=crawler_name)
            glue.update_crawler(**crawler_args)
        except glue.exceptions.EntityNotFoundException:
            glue.create_crawler(**crawler_args)
        return crawler_name

    @task()
    def run_glue_crawler(cfg, crawl_name: str):
        import traceback
        glue = boto3.client("glue", region_name=cfg["region"])
        
        try:
            # Verificar estado actual del crawler
            print(f"🔍 Verificando estado del crawler '{crawl_name}'...")
            details = glue.get_crawler(Name=crawl_name)
            state = details["Crawler"]["State"]
            print(f"📊 Estado actual: {state}")
            
            # Si está corriendo, esperar a que termine
            if state == "RUNNING":
                print("⏳ Crawler ya está en ejecución, esperando...")
                while True:
                    details = glue.get_crawler(Name=crawl_name)
                    state = details["Crawler"]["State"]
                    if state == "READY":
                        print("✅ Crawler anterior completado")
                        break
                    print(f"  ⏳ Estado: {state}, esperando 15s...")
                    time.sleep(15)
            
            # Iniciar el crawler
            print(f"🚀 Iniciando crawler '{crawl_name}'...")
            try:
                glue.start_crawler(Name=crawl_name)
                print("✅ Crawler iniciado exitosamente")
            except Exception as e:
                if "CrawlerRunningException" in str(e):
                    print("⚠️  Crawler ya está en ejecución")
                else:
                    raise
            
            # Esperar a que complete
            print("⏳ Esperando a que el crawler complete...")
            max_wait = 600  # 10 minutos máximo
            elapsed = 0
            
            while elapsed < max_wait:
                time.sleep(15)
                elapsed += 15
                
                details = glue.get_crawler(Name=crawl_name)
                state = details["Crawler"]["State"]
                last_crawl = details["Crawler"].get("LastCrawl", {})
                
                print(f"  [{elapsed}s] Estado: {state}")
                
                if state == "READY":
                    status = last_crawl.get("Status", "UNKNOWN")
                    tables_created = last_crawl.get("TablesCreated", 0)
                    tables_updated = last_crawl.get("TablesUpdated", 0)
                    tables_deleted = last_crawl.get("TablesDeleted", 0)
                    
                    print(f"\n📊 Crawler completado:")
                    print(f"  ✅ Estado: {status}")
                    print(f"  📋 Tablas creadas: {tables_created}")
                    print(f"  🔄 Tablas actualizadas: {tables_updated}")
                    print(f"  ❌ Tablas eliminadas: {tables_deleted}")
                    
                    if status == "SUCCEEDED":
                        return {
                            "crawler": crawl_name,
                            "status": "SUCCEEDED",
                            "tables_created": tables_created,
                            "tables_updated": tables_updated
                        }
                    else:
                        print(f"⚠️  Crawler terminó con estado: {status}")
                        error_msg = last_crawl.get("ErrorMessage", "Sin mensaje de error")
                        print(f"❌ Error: {error_msg}")
                        return {
                            "crawler": crawl_name,
                            "status": status,
                            "error": error_msg
                        }
            
            print(f"❌ Timeout: Crawler no completó en {max_wait}s")
            return {
                "crawler": crawl_name,
                "status": "TIMEOUT",
                "error": f"Crawler no completó en {max_wait} segundos"
            }
                    
        except Exception as e:
            error_msg = f"Error ejecutando crawler: {str(e)}"
            print(f"❌ {error_msg}")
            print(f"Stack trace: {traceback.format_exc()}")
            raise

    configuration = load_config()
    bucket_ready = ensure_bucket(configuration)
    exports = export_tables(configuration)
    database = ensure_glue_database(configuration)
    crawler_name = ensure_glue_crawler(configuration)
    crawler_run = run_glue_crawler(configuration, crawler_name)

    bucket_ready >> exports >> database >> crawler_name >> crawler_run