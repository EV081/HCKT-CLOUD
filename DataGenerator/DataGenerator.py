import json
import uuid
from datetime import datetime, timedelta
from pathlib import Path
import random
import os

# Configuración
OUTPUT_DIR = Path(__file__).parent / "example-data"
SCHEMAS_DIR = Path(__file__).parent / "schemas-validation"

# Datos base para generar ejemplos realistas
NOMBRES = [
    "Juan Pérez", "María García", "Carlos López", "Ana Martínez",
    "Luis Rodríguez", "Carmen Fernández", "José González", "Laura Sánchez",
    "Miguel Torres", "Isabel Ramírez", "Pedro Flores", "Sofía Castro",
    "Diego Morales", "Valentina Ortiz", "Andrés Silva", "Camila Rojas"
]

CORREOS_DOMINIOS = ["utec.edu.pe", "gmail.com", "outlook.com"]

TITULOS_INCIDENTES = [
    "Fuga de agua en baño",
    "Luz fundida en pasillo",
    "Ventana rota en aula",
    "Piso resbaladizo",
    "Puerta atascada",
    "Aire acondicionado no funciona",
    "Proyector dañado",
    "Silla rota",
    "Mesa inestable",
    "Escalera con pasamanos suelto"
]

DESCRIPCIONES_INCIDENTES = [
    "Se requiere atención inmediata",
    "Problema detectado durante inspección de rutina",
    "Reportado por múltiples usuarios",
    "Afecta el uso normal del área",
    "Necesita reparación urgente",
    "Situación de riesgo para estudiantes",
    "Problema recurrente en esta área",
    "Requiere evaluación por especialista"
]

SERVICIOS = ["usuarios", "incidentes", "notificaciones", "analitica", "conexiones"]

MENSAJES_LOG = [
    "Usuario autenticado exitosamente",
    "Error al procesar solicitud",
    "Conexión establecida",
    "Timeout en operación",
    "Datos guardados correctamente",
    "Error de validación",
    "Servicio iniciado",
    "Operación completada"
]

AUTHORITY_NAME = os.getenv("AUTHORITY_USUARIO_NOMBRE", "Autoridad UTEC")
AUTHORITY_EMAIL = os.getenv("AUTHORITY_USUARIO_CORREO", "autoridad@utec.edu.pe")
AUTHORITY_PASSWORD = os.getenv("AUTHORITY_USUARIO_CONTRASENA", "autoridad123")

USUARIOS_TOTAL = int(os.getenv("USUARIOS_TOTAL", "30"))
EMPLEADOS_TOTAL = int(os.getenv("EMPLEADOS_TOTAL", "50"))
INCIDENTES_TOTAL = int(os.getenv("INCIDENTES_TOTAL", "20"))
REGISTROS_TOTAL = int(os.getenv("REGISTROS_TOTAL", "10"))
CONEXIONES_TOTAL = int(os.getenv("CONEXIONES_TOTAL", "10"))

TIPOS_AREA = [
    "limpieza", "seguridad", "mantenimiento",
    "electricidad", "ti", "logistica", "otro"
]
ESTADOS_EMPLEADOS = ["activo", "inactivo"]


def generar_correo(nombre):
    """Genera un correo electrónico basado en el nombre"""
    nombre_limpio = nombre.lower().replace(" ", ".")
    dominio = random.choice(CORREOS_DOMINIOS)
    return f"{nombre_limpio}@{dominio}"


def generar_telefono():
    """Genera un número de teléfono peruano"""
    return f"+51 9{random.randint(10000000, 99999999)}"


def generar_usuarios(cantidad=None):
    usuarios = []
    roles_no_autoridad = ["estudiante", "personal_administrativo"]
    objetivo = max(1, cantidad or USUARIOS_TOTAL)
    
    autoridad = {
        "correo": AUTHORITY_EMAIL,
        "contrasena": AUTHORITY_PASSWORD,
        "nombre": AUTHORITY_NAME,
        "rol": "autoridad"
    }
    usuarios.append(autoridad)
    correos_usados = {AUTHORITY_EMAIL}
    
    while len(usuarios) < objetivo:
        nombre = random.choice(NOMBRES)
        correo = generar_correo(nombre)
        if correo in correos_usados:
            continue
        usuarios.append({
            "correo": correo,
            "contrasena": f"hash_{uuid.uuid4().hex[:16]}",
            "nombre": nombre,
            "rol": random.choice(roles_no_autoridad)
        })
        correos_usados.add(correo)
    
    if not any(u["rol"] == "estudiante" for u in usuarios):
        while True:
            nombre = random.choice(NOMBRES)
            correo = generar_correo(nombre)
            if correo in correos_usados:
                continue
            usuarios.append({
                "correo": correo,
                "contrasena": f"hash_{uuid.uuid4().hex[:16]}",
                "nombre": nombre,
                "rol": "estudiante"
            })
            correos_usados.add(correo)
            break
    
    return usuarios


def generar_empleados(cantidad=None):
    empleados = []
    cantidad = max(1, cantidad or EMPLEADOS_TOTAL)
    
    base = cantidad // len(TIPOS_AREA)
    residuo = cantidad % len(TIPOS_AREA)
    plan = []
    for idx, tipo in enumerate(TIPOS_AREA):
        repeticiones = base + (1 if idx < residuo else 0)
        plan.extend([tipo] * repeticiones)
    if len(plan) > cantidad:
        plan = plan[:cantidad]
    
    for tipo_area in plan:
        nombre = random.choice(NOMBRES)
        empleados.append({
            "empleado_id": str(uuid.uuid4()),
            "nombre": nombre,
            "tipo_area": tipo_area,
            "estado": random.choice(ESTADOS_EMPLEADOS) if random.random() > 0.2 else "activo",
            "contacto": {
                "telefono": generar_telefono(),
                "correo": generar_correo(nombre)
            }
        })
    
    return empleados


def generar_incidentes(usuarios, empleados, cantidad=None):
    """Genera datos de ejemplo para incidentes"""
    incidentes = []
    cantidad = max(1, cantidad or INCIDENTES_TOTAL)
    tipos = ["limpieza", "seguridad", "mantenimiento", "electricidad", "ti", "logistica", "otro"]
    niveles_urgencia = ["bajo", "medio", "alto", "critico"]
    estados = ["reportado", "en_progreso", "resuelto"]
    
    estudiantes = [u for u in usuarios if u.get("rol") == "estudiante"]
    if not estudiantes:
        raise ValueError("Se requieren usuarios con rol 'estudiante' para generar incidentes")
    
    empleados_activos = [e for e in empleados if e.get("estado") == "activo"]
    if not empleados_activos:
        print("⚠️  Advertencia: No hay empleados activos. Los incidentes en progreso/resueltos no tendrán empleado asignado.")
    
    for i in range(cantidad):
        creado_en = datetime.now() - timedelta(days=random.randint(0, 30))
        tiene_actualizacion = random.random() > 0.5
        estado = random.choice(estados)
        
        incidente = {
            "incidente_id": str(uuid.uuid4()),
            "titulo": random.choice(TITULOS_INCIDENTES),
            "descripcion": random.choice(DESCRIPCIONES_INCIDENTES),
            "piso": random.randint(1, 5),
            "ubicacion": {
                "x": round(random.uniform(-77.0, -76.9), 6),
                "y": round(random.uniform(-12.1, -12.0), 6)
            },
            "tipo": random.choice(tipos),
            "nivel_urgencia": random.choice(niveles_urgencia),
            "evidencias": [
                f"https://storage.example.com/evidencias/{uuid.uuid4()}.jpg"
            ] if random.random() > 0.3 else [],
            "estado": estado,
            "usuario_correo": random.choice(estudiantes)["correo"],
            "creado_en": creado_en.isoformat()
        }
        
        # Asignar empleado_correo solo si el estado es "en_progreso" o "resuelto"
        if estado in ["en_progreso", "resuelto"] and empleados_activos:
            empleado = random.choice(empleados_activos)
            incidente["empleado_correo"] = empleado["contacto"]["correo"]
        
        if tiene_actualizacion:
            incidente["actualizado_en"] = (creado_en + timedelta(hours=random.randint(1, 48))).isoformat()
        
        incidentes.append(incidente)
    
    return incidentes


def generar_registros(cantidad=None):
    """Genera datos de ejemplo para registros (logs)"""
    registros = []
    cantidad = max(1, cantidad or REGISTROS_TOTAL)
    niveles = ["INFO", "WARNING", "ERROR", "CRITICAL"]
    operaciones = ["creacion", "actualizacion", "eliminacion", "consulta"]
    correos_estandar = [
        "auditoria@utec.edu.pe", "admin@utec.edu.pe",
        "personal@utec.edu.pe", "estudiante@utec.edu.pe"
    ]
    
    for i in range(cantidad):
        tipo = random.choice(["sistema", "auditoria", "sistema", "sistema"])
        nivel = "AUDIT" if tipo == "auditoria" else random.choice(niveles)
        servicio = random.choice(SERVICIOS)

        registro = {
            "registro_id": str(uuid.uuid4()),
            "nivel": nivel,
            "tipo": tipo,
            "marca_tiempo": (datetime.now() - timedelta(hours=random.randint(0, 72))).isoformat()
        }

        if tipo == "auditoria":
            entidad = random.choice(["usuarios", "incidentes", "empleados", "conexiones"])
            operacion = random.choice(operaciones)
            registro["detalles_auditoria"] = {
                "usuario_correo": random.choice(correos_estandar),
                "entidad": entidad,
                "entidad_id": str(uuid.uuid4()),
                "operacion": operacion,
                "valores_previos": {
                    "estado": random.choice(["reportado", "en_progreso", "resuelto"])
                } if operacion in {"actualizacion", "eliminacion"} else {},
                "valores_nuevos": {
                    "estado": random.choice(["reportado", "en_progreso", "resuelto"])
                } if operacion in {"creacion", "actualizacion"} else {}
            }
        else:
            registro["detalles_sistema"] = {
                "mensaje": random.choice(MENSAJES_LOG),
                "servicio": servicio,
                "contexto": {
                    "request_id": str(uuid.uuid4()),
                    "user_agent": "AWS Lambda",
                    "ip": f"192.168.{random.randint(1, 255)}.{random.randint(1, 255)}"
                }
            }

        registros.append(registro)

    return registros


def generar_conexiones(usuarios, cantidad=None):
    """Genera datos de ejemplo para conexiones WebSocket"""
    conexiones = []
    cantidad = max(1, cantidad or CONEXIONES_TOTAL)
    
    for i in range(cantidad):
        created_at = datetime.now() - timedelta(minutes=random.randint(0, 120))
        expiracion_ttl = int((created_at + timedelta(hours=4)).timestamp())
        
        usuario = random.choice(usuarios)
        
        conexion = {
            "conexion_id": str(uuid.uuid4()),
            "usuario_correo": usuario["correo"],
            "rol": usuario.get("rol", "estudiante"),
            "created_at": created_at.isoformat(),
            "expiracion_ttl": expiracion_ttl
        }
        conexiones.append(conexion)
    
    return conexiones


def validar_con_esquema(datos, nombre_esquema):
    """Valida que los datos cumplan con el esquema definido"""
    try:
        with open(SCHEMAS_DIR / f"{nombre_esquema}.json", "r", encoding="utf-8") as f:
            esquema = json.load(f)
        
        # Verificar propiedades requeridas
        required = esquema.get("required", [])
        for item in datos:
            for campo in required:
                if campo not in item:
                    print(f"⚠️  Advertencia: Falta campo requerido '{campo}' en {nombre_esquema}")
                    return False
        
        print(f"✅ Datos de {nombre_esquema} validados correctamente")
        return True
    except Exception as e:
        print(f"❌ Error al validar {nombre_esquema}: {e}")
        return False


def guardar_json(datos, nombre_archivo):
    """Guarda los datos en un archivo JSON"""
    OUTPUT_DIR.mkdir(exist_ok=True)
    ruta = OUTPUT_DIR / nombre_archivo
    
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump(datos, f, indent=2, ensure_ascii=False)
    
    print(f"📝 Generado: {ruta} ({len(datos)} registros)")


def main():
    """Función principal que orquesta la generación de datos"""
    print("=" * 60)
    print("🚀 GENERADOR DE DATOS - HCKT-CLOUD")
    print("=" * 60)
    print()
    
    # Generar usuarios primero (son referenciados por otros)
    print("📊 Generando usuarios...")
    usuarios = generar_usuarios()
    validar_con_esquema(usuarios, "usuarios")
    guardar_json(usuarios, "usuarios.json")
    print()
    
    # Generar empleados
    print("📊 Generando empleados...")
    empleados = generar_empleados()
    validar_con_esquema(empleados, "empleados")
    guardar_json(empleados, "empleados.json")
    print()
    
    # Generar incidentes (requiere usuarios y empleados)
    print("📊 Generando incidentes...")
    incidentes = generar_incidentes(usuarios, empleados)
    validar_con_esquema(incidentes, "incidentes")
    guardar_json(incidentes, "incidentes.json")
    print()
    
    # Generar registros
    print("📊 Generando registros (logs)...")
    registros = generar_registros()
    validar_con_esquema(registros, "logs")
    guardar_json(registros, "logs.json")
    print()
    
    # Generar conexiones (requiere usuarios)
    print("📊 Generando conexiones...")
    conexiones = generar_conexiones(usuarios)
    validar_con_esquema(conexiones, "conexiones")
    guardar_json(conexiones, "conexiones.json")
    print()
    
    print("=" * 60)
    print("✨ Generación completada exitosamente")
    print(f"📂 Archivos guardados en: {OUTPUT_DIR}")
    print("=" * 60)


if __name__ == "__main__":
    main()
