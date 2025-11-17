### Alerta UTEC

Este documento proporciona una guía rápida del proyecto **Alerta UTEC** y muestra cómo usar los servicios incluidos en la colección de Postman adjunta. Atención: el despliegue no se realiza con `sls deploy` de forma directa — vea la sección de despliegue.

### Variables de entorno (breve)

A continuación se listan las variables de entorno más relevantes y su propósito general. Estas deben configurarse antes del despliegue (revisar `serverless.yml` y `setup_backend.sh`).

- `TABLE_INCIDENTES`: tabla DynamoDB donde se almacenan los incidentes.
- `TABLE_USUARIOS`: tabla DynamoDB de usuarios y credenciales.
- `TABLE_LOGS`: tabla DynamoDB para logs y auditoría.
- `TABLE_CONEXIONES`: tabla DynamoDB para almacenar conexiones WebSocket activas.
- `INCIDENTES_BUCKET`: bucket S3 donde se guardan evidencias/ficheros relacionados a incidentes.
- `LAMBDA_NOTIFY_INCIDENTE`: nombre/ARN de la Lambda encargada de notificaciones (invocada desde handlers).
- `WEBSOCKET_API_ENDPOINT`: endpoint del API Gateway WebSocket para enviar mensajes.
- `BREVO_API_KEY`, `EMAIL_FROM`: credenciales para envío de correos (Brevo) y dirección remitente.


### Nota de despliegue (IMPORTANTE)

No use `sls deploy` directamente sin preparar los recursos. Use el script de orquestación `./setup_backend.sh` en la raíz del repositorio. Ese script crea tablas DynamoDB requeridas, instala dependencias, genera datos de ejemplo y finalmente ejecuta el despliegue ordenado con Serverless Framework.

Ejemplo (rápido):
### Servicios Disponibles

1) Usuarios

   El servicio `Usuarios` gestiona registro, login y la administración de usuarios y empleados.

   Endpoints disponibles:

   - Registrar Usuario
     - Método: POST
     - URL: `{{baserUrl_usuarios}}/usuario/crear`
     - Cuerpo:

      ```json
      {
        "nombre": "Yaritza Lopez",
        "correo": "yartiza.lopez@utec.edu.pe",
        "contrasena": "yaritza123"
      }
      ```

   - Login Usuario
     - Método: POST
     - URL: `{{baserUrl_usuarios}}/usuario/login`
     - Cuerpo:

      ```json
      {
        "correo": "{{correo_estudiante}}",
        "contrasena": "{{contrasena_estudiante}}"
      }
      ```

   - Obtener Mi Usuario
     - Método: GET
     - URL: `{{baserUrl_usuarios}}/usuario/mi`
     - Headers: `Authorization: Bearer <token>`

   - Modificar Usuario
     - Método: PUT
     - URL: `{{baserUrl_usuarios}}/usuario/modificar`
     - Headers: `Authorization: Bearer <token>`
     - Cuerpo ejemplo:

      ```json
      {
        "correo": "{{correo_estudiante}}",
        "nombre": "Nombre Actualizado",
        "contrasena": "{{contrasena_estudiante}}"
      }
      ```

   - Eliminar Usuario
     - Método: DELETE
     - URL: `{{baserUrl_usuarios}}/usuario/eliminar`
     - Headers: `Authorization: Bearer <token>`
     - Cuerpo ejemplo:

      ```json
      {
        "correo": "{{correo_estudiante}}"
      }
      ```

   - Obtener Usuario (por correo)
     - Método: GET
     - URL: `{{baserUrl_usuarios}}/usuario/obtener?correo=<correo>`
     - Headers: `Authorization: Bearer <token>`

   - Listar Usuarios (paginado)
     - Método: POST
     - URL: `{{baserUrl_usuarios}}/usuario/listar`
     - Headers: `Authorization: Bearer <token>`
     - Cuerpo ejemplo:

      ```json
      {
        "limit": 5,
        "last_key": "{{usuarios_last_key}}"
      }
      ```

   - Cambiar Contraseña
     - Método: POST
     - URL: `{{baserUrl_usuarios}}/usuario/cambiar-contrasena`
     - Headers: `Authorization: Bearer <token>`
     - Cuerpo ejemplo:

      ```json
      {
        "contrasena_actual": "{{contrasena_estudiante}}",
        "nueva_contrasena": "yaritza456"
      }
      ```

   - Empleados (crear/listar/modificar/eliminar)
    - Crear Empleado: `POST {{baserUrl_usuarios}}/empleados/crear`

      ```json
      {
        "nombre": "Técnico Soporte",
        "tipo_area": "ti",
        "estado": "activo",
        "contacto": {
          "telefono": "+51 900000001",
          "correo": "soporte.ti@utec.edu.pe"
        }
      }
      ```

    - Listar Empleados: `POST {{baserUrl_usuarios}}/empleados/listar` (paginado/filtrado)

      ```json
      {
        "limit": 5,
        "last_key": "{{empleados_last_key}}",
        "estado": "activo"
      }
      ```

    - Modificar Empleado: `PUT {{baserUrl_usuarios}}/empleados/modificar`

      ```json
      {
        "empleado_id": "{{empleado_id}}",
        "nombre": "Técnico Soporte",
        "tipo_area": "ti",
        "estado": "activo",
        "contacto": {
          "telefono": "+51 900000001",
          "correo": "soporte.ti@utec.edu.pe"
        }
      }
      ```

    - Eliminar Empleado: `DELETE {{baserUrl_usuarios}}/empleados/eliminar`

      ```json
      {
        "empleado_id": "{{empleado_id}}"
      }
      ```

2. **Incidentes**

   Gestión de reportes de incidentes, evidencias y estados.

   - **Crear Incidente**
     - Método: POST
     - URL: `{{baserUrl_incidentes}}/incidente/create`
     - Headers: `Authorization: Bearer <token>`
     - Cuerpo de la solicitud:

       ```json
       {
         "titulo": "Luz quemada",
         "descripcion": "Falla en pasillo",
         "piso": 2,
         "ubicacion": "Bloque A",
         "tipo": "mantenimiento",
         "nivel_urgencia": "medio",
         "coordenadas": { "lat": -12.0, "lng": -77.0 },
         "evidencias": { "file_base64": "<base64>" }
       }
       ```

   - **Listar Incidentes (paginado)**
     - Método: POST
     - URL: `{{baserUrl_incidentes}}/incidente/list`
     - Headers: `Authorization: Bearer <token>`
     - Cuerpo (opcional, soporta filtros):

       ```json
       {
         "page": 0,
         "size": 10,
         "estado": "en_progreso",    // opcional: filtra por estado
         "tipo": "mantenimiento",    // opcional: filtra por tipo
         "nivel_urgencia": "medio"   // opcional: filtra por nivel_urgencia
       }
       ```

     - Comportamiento por rol (respuesta):
       - Si el solicitante es **estudiante**, cada item en `contents` contiene campos resumidos:

         ```json
         {
           "titulo": "...",
           "piso": 2,
           "tipo": "mantenimiento",
           "nivel_urgencia": "medio",
           "estado": "en_progreso",
           "created_at": "2025-11-01T12:00:00Z",
           "updated_at": "2025-11-02T08:00:00Z"
         }
         ```

       - Si el solicitante es **autoridad** o **administrador_empleado**, recibe detalle completo por item:

         ```json
         {
           "incidente_id": "<uuid>",
           "titulo": "...",
           "descripcion": "...",
           "piso": 2,
           "ubicacion": "Bloque A",
           "tipo": "mantenimiento",
           "nivel_urgencia": "medio",
           "evidencias": [],
           "estado": "en_progreso",
           "usuario_correo": "user@utec.edu.pe",
           "created_at": "2025-11-01T12:00:00Z",
           "updated_at": "2025-11-02T08:00:00Z",
           "coordenadas": { "lat": -12.0, "lng": -77.0 }
         }
         ```

       - Respuesta paginada (ambos casos):

         ```json
         {
           "contents": [ /* items */ ],
           "page": 0,
           "size": 10,
           "totalElements": 123,
           "totalPages": 13
         }
         ```

   - **Buscar Incidente (por ID)**
     - Método: POST
     - URL: `{{baserUrl_incidentes}}/incidente/search`
     - Headers: `Authorization: Bearer <token>`
     - Cuerpo:

       ```json
       { "incidente_id": "<uuid>" }
       ```

     - Permisos: sólo pueden consultar **autoridad**, **administrador_empleado** o el **propietario** (usuario que creó el incidente). La respuesta devuelve toda la información disponible del incidente (campos completos mostrados arriba).

   - **Actualizar Incidente (usuario dueño)**
     - Método: POST
     - URL: `{{baserUrl_incidentes}}/incidente/update`
     - Headers: `Authorization: Bearer <token>`
     - Permisos: sólo el **propietario** puede actualizar su incidente.
     - Cuerpo (ejemplo):

       ```json
       {
         "incidente_id": "{{incidente_id}}",
         "titulo": "Fuga de agua actualizada",
         "descripcion": "Actualización del incidente por el estudiante.",
         "piso": 3,
         "ubicacion": { "x": -76.88, "y": -12.88 },
         "tipo": "mantenimiento",
         "nivel_urgencia": "medio"
       }
       ```

   - **Cambiar Estado (admin)**
     - Método: POST
     - URL: `{{baserUrl_incidentes}}/incidente/change-state`
     - Headers: `Authorization: Bearer <token>` (roles: `personal_administrativo`, `autoridad`)
     - Cuerpo (ejemplos):

       - Marcar como en_progreso (requiere `empleado_correo`):

         ```json
         { "incidente_id": "<uuid>", "estado": "en_progreso", "empleado_correo": "empleado@utec.edu.pe" }
         ```

       - Marcar como resuelto (no requiere `empleado_correo`):

         ```json
         { "incidente_id": "<uuid>", "estado": "resuelto" }
         ```

   - **Historial (mis incidentes)**
     - Método: POST
     - URL: `{{baserUrl_incidentes}}/incidentes/historial`
     - Headers: `Authorization: Bearer <token>` (token de estudiante)
     - Cuerpo (opcional, soporta filtros iguales a `list`):

       ```json
       {
         "page": 0,
         "size": 10,
         "estado": "resuelto"   // opcional
       }
       ```

     - Respuesta: igual al formato paginado de `list`, pero contiene sólo los incidentes del usuario autenticado.

   - **Notas adicionales**
     - El filtrado por `tipo`, `estado` y `nivel_urgencia` está soportado en los listados y en el historial.
     - Las rutas y permisos siguen la lógica implementada en `list_report.py`, `search_report.py`, `update_report_users.py` y `update_report_admin.py`.
       ```

3. **Notificaciones (HTTP + WebSocket)**

   - **Notificar incidente (HTTP -> broadcast WS)**
     - Método: POST
     - URL: `{{baserUrl_notificaciones}}/notificaciones/incidente`
     - Cuerpo de la solicitud (ejemplo):

      ```json
      {
        "incidente_id": "INC-001",
        "estado": "EN_PROCESO",
        "destinatarios": ["{{correo_estudiante}}"],
        "datos": {
          "mensaje": "Prueba de notificación"
        }
      }
      ```

   - **WebSocket $connect**
     - URL (WebSocket): `wss://<websocket-endpoint>/?token=<jwt>`
     - El parámetro `token` es obligatorio; la Lambda guarda la conexión en `TABLE_CONEXIONES`.

4. **Analítica**

   Endpoints para triggers y reportes analíticos (ETL/Airflow).

   - **Trigger ETL**
     - Método: POST
     - URL: `{{baserUrl_analitica}}/analitica/trigger-etl`

    - **Incidentes por piso**
      - Método: GET
      - URL: `{{baserUrl_analitica}}/analitica/incidentes-por-piso`
      - Respuesta (ejemplo):

        ```json
        {
          "descripcion": "Análisis de incidentes por piso y estado",
          "resultados": [
            { "piso": "1", "estado": "en_progreso", "total_incidentes": "1" },
            { "piso": "1", "estado": "reportado", "total_incidentes": "3" },
            { "piso": "1", "estado": "resuelto", "total_incidentes": "1" },
            { "piso": "2", "estado": "en_progreso", "total_incidentes": "2" },
            { "piso": "2", "estado": "reportado", "total_incidentes": "1" },
            { "piso": "2", "estado": "resuelto", "total_incidentes": "4" },
            { "piso": "3", "estado": "en_progreso", "total_incidentes": "1" },
            { "piso": "3", "estado": "reportado", "total_incidentes": "1" },
            { "piso": "3", "estado": "resuelto", "total_incidentes": "1" },
            { "piso": "4", "estado": "reportado", "total_incidentes": "3" },
            { "piso": "5", "estado": "reportado", "total_incidentes": "1" },
            { "piso": "5", "estado": "resuelto", "total_incidentes": "1" }
          ],
          "total_filas": 12
        }
        ```

    - **Incidentes por tipo**
      - Método: GET
      - URL: `{{baserUrl_analitica}}/analitica/incidentes-por-tipo`
      - Respuesta (ejemplo):

        ```json
        {
          "descripcion": "Distribución de incidentes por tipo y nivel de urgencia",
          "resultados": [
            { "tipo": "TI", "nivel_urgencia": "alto", "cantidad": "3", "porcentaje": "15.0" },
            { "tipo": "TI", "nivel_urgencia": "medio", "cantidad": "2", "porcentaje": "10.0" },
            { "tipo": "limpieza", "nivel_urgencia": "medio", "cantidad": "1", "porcentaje": "5.0" },
            { "tipo": "mantenimiento", "nivel_urgencia": "alto", "cantidad": "1", "porcentaje": "5.0" },
            { "tipo": "mantenimiento", "nivel_urgencia": "bajo", "cantidad": "1", "porcentaje": "5.0" },
            { "tipo": "mantenimiento", "nivel_urgencia": "critico", "cantidad": "2", "porcentaje": "10.0" },
            { "tipo": "mantenimiento", "nivel_urgencia": "medio", "cantidad": "2", "porcentaje": "10.0" },
            { "tipo": "otro", "nivel_urgencia": "alto", "cantidad": "2", "porcentaje": "10.0" },
            { "tipo": "otro", "nivel_urgencia": "bajo", "cantidad": "2", "porcentaje": "10.0" },
            { "tipo": "otro", "nivel_urgencia": "critico", "cantidad": "1", "porcentaje": "5.0" },
            { "tipo": "seguridad", "nivel_urgencia": "bajo", "cantidad": "2", "porcentaje": "10.0" },
            { "tipo": "seguridad", "nivel_urgencia": "medio", "cantidad": "1", "porcentaje": "5.0" }
          ],
          "total_filas": 12
        }
        ```

    - **Tiempo de resolución**
      - Método: GET
      - URL: `{{baserUrl_analitica}}/analitica/tiempo-resolucion`
      - Respuesta (ejemplo):

        ```json
        {
          "descripcion": "Análisis de tiempo de resolución de incidentes",
          "resultados": [
            {
              "incidente_id": "59dd3d6d-a55d-4830-84eb-05de0edbd724",
              "titulo": "Aire acondicionado no funciona",
              "tipo": "TI",
              "nivel_urgencia": "alto",
              "creado_en": "2025-10-29T18:10:11.583441",
              "actualizado_en": "2025-10-30T00:10:11.583441",
              "estado": "resuelto",
              "horas_resolucion": "6"
            },
            {
              "incidente_id": "60943c48-94dc-439a-8ac0-907731142b33",
              "titulo": "Proyector dañado",
              "tipo": "TI",
              "nivel_urgencia": "alto",
              "creado_en": "2025-11-07T18:10:11.583661",
              "actualizado_en": "2025-11-08T04:10:11.583661",
              "estado": "resuelto",
              "horas_resolucion": "10"
            },
            {
              "incidente_id": "cdb2f3e9-83e2-45ac-88c5-e8958e56187d",
              "titulo": "Aire acondicionado no funciona",
              "tipo": "mantenimiento",
              "nivel_urgencia": "critico",
              "creado_en": "2025-10-26T18:10:11.583525",
              "actualizado_en": "2025-10-27T16:10:11.583525",
              "estado": "resuelto",
              "horas_resolucion": "22"
            },
            {
              "incidente_id": "2d766683-04da-45ca-8fd5-bf5eda2f62c4",
              "titulo": "Silla rota",
              "tipo": "mantenimiento",
              "nivel_urgencia": "critico",
              "creado_en": "2025-10-30T18:10:11.583472",
              "actualizado_en": "2025-11-01T01:10:11.583472",
              "estado": "resuelto",
              "horas_resolucion": "31"
            },
            {
              "incidente_id": "d0395135-1ca6-4436-b823-5ff3db59a180",
              "titulo": "Ventana rota en aula",
              "tipo": "otro",
              "nivel_urgencia": "bajo",
              "creado_en": "2025-11-05T18:10:11.583584",
              "actualizado_en": null,
              "estado": "resuelto",
              "horas_resolucion": null
            },
            {
              "incidente_id": "3201aeeb-588a-4b1d-ba28-baceaa98a306",
              "titulo": "Proyector dañado",
              "tipo": "limpieza",
              "nivel_urgencia": "medio",
              "creado_en": "2025-11-06T18:10:11.583629",
              "actualizado_en": null,
              "estado": "resuelto",
              "horas_resolucion": null
            },
            {
              "incidente_id": "94706d8c-18c3-42af-b775-5f9b8caa99a1",
              "titulo": "Silla rota",
              "tipo": "otro",
              "nivel_urgencia": "alto",
              "creado_en": "2025-10-27T18:10:11.583643",
              "actualizado_en": null,
              "estado": "resuelto",
              "horas_resolucion": null
            }
          ],
          "total_filas": 7
        }
        ```

    - **Reportes por usuario**
      - Método: GET
      - URL: `{{baserUrl_analitica}}/analitica/reportes-por-usuario`
      - Respuesta (ejemplo):

        ```json
        {
          "descripcion": "Top 20 usuarios estudiantes por cantidad de reportes",
          "resultados": [
            {
              "usuario_correo": "miguel.torres@gmail.com",
              "nombre": "Miguel Torres",
              "rol": "estudiante",
              "total_reportes": "4",
              "reportes_resueltos": "1",
              "reportes_en_progreso": "1",
              "reportes_pendientes": "2"
            },
            {
              "usuario_correo": "maría.garcía@outlook.com",
              "nombre": "María García",
              "rol": "estudiante",
              "total_reportes": "3",
              "reportes_resueltos": "1",
              "reportes_en_progreso": "0",
              "reportes_pendientes": "2"
            },
            {
              "usuario_correo": "ana.martínez@outlook.com",
              "nombre": "Ana Martínez",
              "rol": "estudiante",
              "total_reportes": "2",
              "reportes_resueltos": "1",
              "reportes_en_progreso": "1",
              "reportes_pendientes": "0"
            }
          ],
          "total_filas": 12
        }
        ```

    - **Requisitos de red para Analítica (VPC / Subnets)**

      Para ejecutar los pipelines de analítica (ECS / Airflow) se requiere configurar `ANALITICA_VPC_ID` y `ANALITICA_SUBNETS` (dos subnets) en las variables de entorno. Las subnets deben indicarse como IDs separados por comas.

      Pasos rápidos para obtenerlos desde la consola de AWS:

      1. Accede a la consola de AWS -> busca y abre el servicio **VPC**.
      2. En el menú izquierdo selecciona **Your VPCs** (o "Tus VPCs"). Localiza la VPC que quieras reutilizar y copia su **VPC ID** (p. ej. `vpc-0a1b2c3d4e5f6g7h`). Ese valor va en `ANALITICA_VPC_ID`.
      3. Ahora ve a **Subnets** en el mismo servicio VPC. Elige dos subnets (por ejemplo, dos subnets privadas o las que tu arquitectura requiera) y copia sus IDs (p. ej. `subnet-aaaaaaaa,subnet-bbbbbbbb`). Pegarlos separados por coma en `ANALITICA_SUBNETS`.

      Ejemplo en `.env` (o `.env.example` ya presente en el repo):

      ```dotenv
      ANALITICA_VPC_ID=vpc-0a1b2c3d4e5f6g7h
      ANALITICA_SUBNETS=subnet-aaaaaaaa,subnet-bbbbbbbb
      ```

      - Nota: por defecto muchas cuentas tienen al menos una VPC; puedes reutilizar esa VPC si cumple los requisitos de red. Asegúrate de escoger subnets con acceso a los recursos necesarios (NAT/Internet o rutas privadas según tu diseño).


5. **Logs**

   - **Listar logs**
     - Método: POST
     - URL: `{{baserUrl_logs}}/logs/list`
     - Headers: `Authorization: Bearer <token>` (solo roles administrativos)
     - Cuerpo (opcional): `{ "page": 0, "size": 20 }`




