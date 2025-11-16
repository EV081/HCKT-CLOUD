#!/bin/bash

set -e  # Salir si hay algún error

# Colores para output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Función para mostrar el menú
show_menu() {
    echo "============================================================"
    echo "🚀 ALERTA UTEC - SETUP BACKEND"
    echo "============================================================"
    echo ""
    echo "Selecciona una opción:"
    echo ""
    echo "  1) 🏗️  Desplegar todo (Infraestructura + Microservicios)"
    echo "  2) 🗑️  Eliminar todo (Microservicios + Infraestructura)"
    echo "  3) 📊 Solo crear infraestructura y poblar datos"
    echo "  4) 🚀 Solo desplegar microservicios"
    echo "  5) ❌ Salir"
    echo ""
}

# Función para verificar .env
check_env() {
    if [ ! -f .env ]; then
        echo -e "${YELLOW}⚠️  Archivo .env no encontrado${NC}"
        echo "Por favor, copia .env.example a .env y configura tus variables"
        exit 1
    fi
    export $(cat .env | grep -v '^#' | xargs)
}

# Función para preparar dependencias
prepare_dependencies() {
    echo -e "\n${BLUE}📦 Preparando Lambda Layer de dependencias...${NC}"
    
    # Crear estructura de directorios si no existe
    mkdir -p Dependencias/python-dependencies/python
    
    # Verificar si requirements.txt existe
    if [ ! -f "Dependencias/requirements.txt" ]; then
        echo -e "${RED}❌ No se encuentra Dependencias/requirements.txt${NC}"
        return 1
    fi
    
    cd Dependencias/python-dependencies
    
    # Verificar si ya existe la carpeta python con paquetes
    if [ -d "python" ] && [ "$(ls -A python 2>/dev/null | wc -l)" -gt 5 ]; then
        echo -e "${GREEN}✅ Dependencias ya están instaladas${NC}"
    else
        echo -e "${YELLOW}📥 Instalando dependencias Python...${NC}"
        pip3 install -r ../requirements.txt -t python/ --upgrade --quiet
        echo -e "${GREEN}✅ Dependencias instaladas en python-dependencies/python/${NC}"
    fi
    
    cd ../..
}

ensure_analitica_bucket() {
  if [ -z "${ANALITICA_S3_BUCKET}" ]; then
    echo -e "${RED}❌ ANALITICA_S3_BUCKET no está definido en .env${NC}"
    exit 1
  fi

  if aws s3api head-bucket --bucket "${ANALITICA_S3_BUCKET}" 2>/dev/null; then
    echo -e "${GREEN}✅ Bucket '${ANALITICA_S3_BUCKET}' disponible${NC}"
  else
    echo -e "${YELLOW}🔨 Creando bucket '${ANALITICA_S3_BUCKET}'...${NC}"
    if [ "${AWS_REGION}" = "us-east-1" ]; then
      aws s3api create-bucket --bucket "${ANALITICA_S3_BUCKET}" >/dev/null
    else
      aws s3api create-bucket --bucket "${ANALITICA_S3_BUCKET}" --create-bucket-configuration LocationConstraint="${AWS_REGION}" >/dev/null
    fi
    aws s3api put-bucket-versioning --bucket "${ANALITICA_S3_BUCKET}" --versioning-configuration Status=Enabled >/dev/null
    aws s3api put-public-access-block --bucket "${ANALITICA_S3_BUCKET}" --public-access-block-configuration BlockPublicAcls=true IgnorePublicAcls=true BlockPublicPolicy=true RestrictPublicBuckets=true >/dev/null
    echo -e "${GREEN}✅ Bucket creado${NC}"
  fi
}

upload_airflow_dag() {
  local source_file="Analitica/etl_dynamodb.py"
  local target_uri="s3://${ANALITICA_S3_BUCKET}/dags/etl_dynamodb.py"

  if [ ! -f "${source_file}" ]; then
    echo -e "${RED}❌ No se encuentra ${source_file}${NC}"
    exit 1
  fi

  echo -e "${BLUE}📤 Subiendo DAG a ${target_uri}...${NC}"
  aws s3 cp "${source_file}" "${target_uri}" >/dev/null
  echo -e "${GREEN}✅ DAG actualizado${NC}"
}

# Función para crear infraestructura
deploy_infrastructure() {
    echo -e "\n${BLUE}🏗️  Creando recursos de infraestructura (Tablas DynamoDB y Bucket S3)...${NC}"
    
    # Instalar dependencias necesarias para DataPoblator (boto3, python-dotenv)
    echo -e "${YELLOW}📦 Instalando dependencias para DataPoblator...${NC}"
    pip3 install -q boto3 python-dotenv
    
    cd DataGenerator
    python3 DataPoblator.py
    cd ..
    echo -e "${GREEN}✅ Infraestructura creada${NC}"
}

# Función para desplegar microservicios
deploy_services() {
    echo -e "\n${BLUE}🚀 Desplegando microservicios con Serverless Compose...${NC}"
    prepare_dependencies
    ensure_analitica_bucket
    upload_airflow_dag
    sls deploy
    echo -e "${GREEN}✅ Microservicios desplegados${NC}"
}

# Función para eliminar microservicios
remove_services() {
    echo -e "\n${RED}🗑️  Eliminando microservicios...${NC}"
    sls remove
    echo -e "${GREEN}✅ Microservicios eliminados${NC}"
}

# Función para eliminar infraestructura
remove_infrastructure() {
    echo -e "\n${RED}🗑️  Eliminando recursos de infraestructura...${NC}"
    
    # Eliminar tablas DynamoDB
    echo -e "${YELLOW}Eliminando tablas DynamoDB...${NC}"
    aws dynamodb delete-table --table-name ${TABLE_USUARIOS} 2>/dev/null || echo "Tabla ${TABLE_USUARIOS} no existe"
    aws dynamodb delete-table --table-name ${TABLE_INCIDENTES} 2>/dev/null || echo "Tabla ${TABLE_INCIDENTES} no existe"
    aws dynamodb delete-table --table-name ${TABLE_EMPLEADOS} 2>/dev/null || echo "Tabla ${TABLE_EMPLEADOS} no existe"
    aws dynamodb delete-table --table-name ${TABLE_LOGS} 2>/dev/null || echo "Tabla ${TABLE_LOGS} no existe"
    aws dynamodb delete-table --table-name ${TABLE_CONEXIONES} 2>/dev/null || echo "Tabla ${TABLE_CONEXIONES} no existe"
    
    # Eliminar bucket S3
    echo -e "${YELLOW}Eliminando bucket S3...${NC}"
    S3_BUCKET="alerta-utec-data-${AWS_ACCOUNT_ID}"
    aws s3 rm s3://${S3_BUCKET} --recursive 2>/dev/null || echo "Bucket ${S3_BUCKET} no existe"
    aws s3 rb s3://${S3_BUCKET} 2>/dev/null || echo "Bucket ${S3_BUCKET} no existe"
    
    echo -e "${GREEN}✅ Infraestructura eliminada${NC}"
}

# Función principal
main() {
    check_env
    
    while true; do
        show_menu
        read -p "Opción: " option
        
        case $option in
            1)
                echo ""
                echo "============================================================"
                echo "🏗️  DESPLIEGUE COMPLETO"
                echo "============================================================"
                deploy_infrastructure
                deploy_services
                echo ""
                echo -e "${GREEN}============================================================${NC}"
                echo -e "${GREEN}🎉 DESPLIEGUE COMPLETADO EXITOSAMENTE${NC}"
                echo -e "${GREEN}============================================================${NC}"
                break
                ;;
            2)
                echo ""
                echo "============================================================"
                echo "🗑️  ELIMINACIÓN COMPLETA"
                echo "============================================================"
                echo -e "${RED}⚠️  ADVERTENCIA: Esto eliminará TODOS los recursos${NC}"
                read -p "¿Estás seguro? (escribe 'SI' para confirmar): " confirm
                if [ "$confirm" = "SI" ]; then
                    remove_services
                    remove_infrastructure
                    echo ""
                    echo -e "${GREEN}============================================================${NC}"
                    echo -e "${GREEN}✅ ELIMINACIÓN COMPLETADA${NC}"
                    echo -e "${GREEN}============================================================${NC}"
                else
                    echo -e "${YELLOW}Operación cancelada${NC}"
                fi
                break
                ;;
            3)
                echo ""
                echo "============================================================"
                echo "📊 SOLO INFRAESTRUCTURA"
                echo "============================================================"
                deploy_infrastructure
                echo ""
                echo -e "${GREEN}✅ Listo${NC}"
                break
                ;;
            4)
                echo ""
                echo "============================================================"
                echo "🚀 SOLO MICROSERVICIOS"
                echo "============================================================"
                deploy_services
                echo ""
                echo -e "${GREEN}✅ Listo${NC}"
                break
                ;;
            5)
                echo -e "${YELLOW}Saliendo...${NC}"
                exit 0
                ;;
            *)
                echo -e "${RED}Opción inválida${NC}"
                ;;
        esac
    done
}

# Ejecutar script
main
