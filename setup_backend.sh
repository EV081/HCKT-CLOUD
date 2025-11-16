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
    
    # Crear estructura base si no existe
    mkdir -p Dependencias/python-dependencies

    # Verificar si requirements.txt existe
    if [ ! -f "Dependencias/requirements.txt" ]; then
        echo -e "${RED}❌ No se encuentra Dependencias/requirements.txt${NC}"
        return 1
    fi
    
    cd Dependencias/python-dependencies

    # 🔥 Siempre limpiar la carpeta python para forzar reinstalación
    rm -rf python
    mkdir -p python

    echo -e "${YELLOW}📥 Instalando dependencias Python (forzado)...${NC}"
    pip3 install -r ../requirements.txt -t python/ --upgrade --quiet
    echo -e "${GREEN}✅ Dependencias instaladas en python-dependencies/python/${NC}"
    
    cd ../..
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
    prepare_dependencies  # ← Agregar esta línea
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
