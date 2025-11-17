**Alerta UTEC — Documentación de Endpoints**

- **Nota de despliegue (importante):** Este proyecto NO se despliega con `sls deploy` de forma directa. Use el script de orquestación definido en la raíz: `setup_backend.sh`. Ese script crea las tablas DynamoDB, instala dependencias, genera datos de ejemplo y ejecuta el despliegue en Serverless Framework en el orden correcto. Revisar/editar `setup_backend.sh` antes de ejecutar en un ambiente de producción.

**Resumen**:
- **Descripción**: Backend serverless para reporte y seguimiento de incidentes en campus UTEC.
- **Tecnologías**: AWS Lambda, API Gateway (HTTP + WebSocket), DynamoDB, S3, (opcional Brevo para emails), Serverless Framework.

**Variables de entorno principales**
- **`TABLE_INCIDENTES`**: tabla DynamoDB de incidentes.
- **`TABLE_USUARIOS`**: tabla DynamoDB de usuarios.
- **`TABLE_LOGS`**: tabla DynamoDB de logs (opcional).
- **`TABLE_CONEXIONES`**: tabla DynamoDB para conexiones WebSocket.
- **`INCIDENTES_BUCKET`**: bucket S3 para evidencias.
- **`LAMBDA_NOTIFY_INCIDENTE`**: nombre/ARN de lambda que envía notificaciones WS.
- **`WEBSOCKET_API_ENDPOINT`**: endpoint del API Gateway WebSocket (para `apigatewaymanagementapi`).
- **`BREVO_API_KEY`, `EMAIL_FROM`**: para envío de correos (opcional).

**Autenticación**
- Todas las rutas protegidas requieren encabezado `Authorization: Bearer <token>` (JWT generado por `CrearUsuario` / sistema de auth). El authorizer Lambda valida y expone context con `correo`, `rol`, `nombre`.

**Endpoints (Lambda handlers)**

- **Crear Incidente** (`Incidentes/CRUD/create_report.py`)
  - Método: POST
  - Headers: `Authorization: Bearer <token>`
  - Roles permitidos: `estudiante`, `personal_administrativo`
  - Body (JSON) requerido:
    - `titulo` (string)
    - `descripcion` (string)
    - `piso` (int entre -2 y 11)
    - `ubicacion` (string)
    - `tipo` (uno de: `limpieza`, `TI`, `seguridad`, `mantenimiento`, `otro`)
    - `nivel_urgencia` (uno de: `bajo`, `medio`, `alto`, `critico`)
    - Opcionales: `coordenadas` {`lat`, `lng`}, `evidencias` {`file_base64`} (sube a S3 si `INCIDENTES_BUCKET` configurado)
  - Respuestas:
    - 201: { `message`, `incidente_id` }
    - 400: validación de campos
    - 401: token inválido
    - 403: rol no autorizado
    - 500: error interno / S3 / DynamoDB
  - Efectos colaterales: guarda auditoría, envía correo de confirmación (Brevo) si configurado, invoca Lambda de notificaciones WS (`LAMBDA_NOTIFY_INCIDENTE`).

- **Listar Incidentes (panel / paginación)** (`Incidentes/CRUD/list_report.py`)
  - Método: POST
  - Headers: `Authorization: Bearer <token>`
  - Roles permitidos: `estudiante`, `personal_administrativo`, `autoridad`
  - Body (JSON) opcional: `page` (int, default 0), `size` (int, default 10)
  - Respuesta 200: { `contents`: [incidentes], `page`, `size`, `totalElements`, `totalPages` }
  - Notas: Para `estudiante` la respuesta incluye solo campos resumidos; para roles administrativos se retorna información completa.

- **Historial de un usuario (mis incidentes)** (`Incidentes/CRUD/historial_list.py`)
  - Método: POST
  - Headers: `Authorization: Bearer <token>`
  - Roles permitidos: `estudiante`, `personal_administrativo`, `autoridad`
  - Body (JSON): `page`, `size` (opcional)
  - Respuesta 200: paginación similar a `list_report`, pero filtrada por `usuario_correo` (historial personal).

- **Buscar incidente por ID** (`Incidentes/CRUD/search_report.py`)
  - Método: POST
  - Headers: `Authorization: Bearer <token>`
  - Body: `{ "incidente_id": "<uuid>" }`
  - Acceso: `personal_administrativo` y `autoridad` pueden ver cualquier incidente; `estudiante` solo su propio incidente.
  - Respuestas:
    - 200: { `message`, `incidente` }
    - 400/401/403/404/500 según caso (validación / permisos / no encontrado / error DB)

- **Actualizar incidente (usuario autor)** (`Incidentes/CRUD/update_report_users.py`)
  - Método: POST
  - Headers: `Authorization: Bearer <token>`
  - Roles permitidos: `estudiante` (solo dueño)
  - Body (JSON) requerido: `incidente_id`, `titulo`, `descripcion`, `piso`, `ubicacion`, `tipo`, `nivel_urgencia` (misma validación que creación)
  - Opcional: `coordenadas`, `evidencias` (base64 -> S3)
  - Respuestas: 200 éxito, 400 validación, 403 no propietario, 404 no encontrado, 500 error interno
  - Efectos: guarda auditoría y `updated_at`.

- **Cambiar estado (admin)** (`Incidentes/CRUD/update_report_admin.py`)
  - Método: POST
  - Headers: `Authorization: Bearer <token>`
  - Roles permitidos: `personal_administrativo`, `autoridad`
  - Body: `{ "incidente_id": "<uuid>", "estado": "en_progreso" | "resuelto" }`
  - Respuestas:
    - 200: { `message`, `incidente_id`, `nuevo_estado` }
    - 400: validación (estado no permitido)
    - 401 / 403 / 404 / 500 según caso
  - Efectos: guarda auditoría, envía correo al creador si configurado, notificación WS (`LAMBDA_NOTIFY_INCIDENTE`).

- **Logs (listar)** (`Logs/list_logs.py`)
  - Método: POST
  - Headers: `Authorization: Bearer <token>`
  - Roles permitidos: `personal_administrativo`, `autoridad`
  - Body: `page`, `size` (opcional)
  - Respuesta 200: paginación con los registros de logs

- **Usuarios: Crear usuario** (`Usuarios/CRUD/CrearUsuario.py`)
  - Método: POST
  - Headers: opcional `Authorization` (si autoridad crea otro usuario)
  - Body: `{ "nombre", "correo", "contrasena", "rol" }`
  - Reglas:
    - Auto-registro sin token solo permite `rol = estudiante`.
    - Si se provee token, solo `autoridad` puede crear usuarios con cualquier rol.
  - Respuestas:
    - 201: `{ message, usuario, token? }` (si se auto-registra devuelve token)
    - 400/403/500 según validación/permiso/error DB
  - Efectos: guarda auditoría, envía correo de bienvenida si Brevo configurado.

- **Usuarios: Login** (`Usuarios/CRUD/LoginUsuario.py`)
  - Método: POST
  - Body: `{ "correo", "contrasena" }`
  - Respuestas:
    - 200: `{ message, token, usuario:{ correo, nombre, rol } }`
    - 400/401/500 según caso

- **Mi Usuario** (`Usuarios/CRUD/MiUsuario.py`)
  - Método: GET
  - Headers: `Authorization` y/o uso del authorizer context
  - Query param opcional: `correo` (solo `autoridad` puede consultar otros usuarios)
  - Respuestas: 200 con datos del usuario (sin contraseña), 403, 404, 500 según caso

- **Authorizer** (`Usuarios/CRUD/Authorizer.py`)
  - Lambda Authorizer que valida el token y retorna contexto con `correo`, `rol`, `nombre`. Lanza `Unauthorized` si inválido.

**WebSocket (Notificaciones)**
- **$connect** (`Notificaciones/handlers/connect.py`)
  - Query string `token` requerido (JWT) para aceptar la conexión
  - Guarda conexión en `TABLE_CONEXIONES` con `conexion_id`, `usuario_correo`, `rol`, TTL
- **$disconnect** (`Notificaciones/handlers/disconnect.py`)
  - Elimina la conexión de `TABLE_CONEXIONES`
- **notify_incidente** (`Notificaciones/handlers/notify_incidente.py`)
  - Invocada internamente (otra Lambda) o vía HTTP
  - Body esperado (si se invoca vía API): `tipo`, `titulo`, `mensaje`, `incidente_id`, `destinatarios` (opcional lista de correos)
  - Envía payload en vivo a conexiones encontradas usando `apigatewaymanagementapi`; elimina conexiones obsoletas (410)

**Comportamiento transversal**
- Auditoría: cada creación/actualización registra un log `auditoria` en `TABLE_LOGS` (si configurada).
- Manejo de números: los handlers convierten `int/float` a `Decimal` para DynamoDB y reconvierten para respuestas JSON.
- Emails: se usan variables `BREVO_API_KEY` y `EMAIL_FROM`. Si faltan, se hacen logs y no se interrumpe la operación.

**Ejemplos rápidos (curl)**
- Login:
  - curl -X POST -H 'Content-Type: application/json' -d '{"correo":"x@utec.edu","contrasena":"123456"}' https://.../usuarios/login
- Crear incidente (ejemplo):
  - curl -X POST -H 'Authorization: Bearer <token>' -H 'Content-Type: application/json' -d '{"titulo":"Luz quemada","descripcion":"Falla en pasillo","piso":2,"ubicacion":"Bloque A","tipo":"mantenimiento","nivel_urgencia":"medio"}' https://.../incidentes/create

**Recomendaciones de despliegue**
- Antes de ejecutar el despliegue verificar variables de entorno en el archivo `serverless.yml` o en el pipeline.
- Ejecutar el script `setup_backend.sh` que: crea tablas, instala dependencias y ejecuta el despliegue ordenado. No usar `sls deploy` manual sin asegurar orden de recursos.

**Requerimientos del sistema**

| # | Requerimiento | Estado |
|---:|---|:---:|
| 1 | Registro y autenticación de usuarios • Registro e inicio con credenciales institucionales • Roles: estudiante, personal_administrativo, autoridad | ✅ |
| 2 | Reporte de incidentes • Crear reportes con tipo, ubicación, descripción, nivel de urgencia • DynamoDB para almacenamiento • Identificador único por reporte | ✅ |
| 3 | Actualización y seguimiento en tiempo real • Actualización de estado con WebSockets • Notificaciones instantáneas en cambios de estado • Estados: pendiente, en atención, resuelto | ✅ |
| 4 | Panel administrativo • Visualizar incidentes activos • Filtrar, priorizar y cerrar reportes • Actualizaciones en tiempo real | ✅ |
| 5 | Orquestación con Apache Airflow • Clasificación automática, envío de notificaciones, generación de reportes periódicos | ✅ (soporte previsto; integrar DAGs en Airflow externo) |
| 6 | Gestión de notificaciones • WebSocket y notificaciones asíncronas (correo/SMS) según gravedad | ✅ |
| 7 | Historial y trazabilidad • Historial completo de acciones (creación/actualizaciones/fechas/responsables) | ✅ |
| 8 | Escalabilidad y resiliencia • Arquitectura serverless, escalado automático de Lambdas y DynamoDB | ✅ |
| 9 | Análisis Predictivo y visualización (Opcional) • Integración con SageMaker para modelos predictivos y visualizaciones | ✅ (opcional, requiere integración adicional) |

Si quieres, puedo:
- generar ejemplos de payload más completos para cada endpoint;
- añadir la lista de variables de entorno por función en el `README`;
- crear un archivo `API.md` separado con ejemplos curl/Postman.

---
Archivo generado automáticamente a partir del código en el repositorio.
# HCKT-CLOUD