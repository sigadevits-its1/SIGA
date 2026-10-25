# SIGA · Sistema Integral de Gestión Académica

Instituto Técnico Superior N.º 1 (Viedma, Río Negro). Primera etapa: **circuito de ingreso**.

- **Formulario público** (`/preinscripcion/`): el aspirante carga sus datos, elige la carrera y adjunta la documentación sin necesitar una cuenta.
- **Bandeja de aspirantes** (`/administracion/`): secretaría consulta solicitudes, filtros y cupos.
- **Ficha** (`/administracion/aspirantes/<id>/`): permite aceptar o rechazar la solicitud completa. Al aceptar, SIGA crea la cuenta de Moodle y envía las credenciales por correo. Al rechazar, envía el motivo para que el aspirante vuelva a completar el formulario.

La documentación del dominio está en [`docs/`](docs/).

## Servicios y direcciones

Un único `docker-compose.yml`, ejecutado desde esta carpeta **SIGA**, levanta todo el proyecto:

| Servicio | Función | Dirección |
|---|---|---|
| `web` | Django / SIGA | http://localhost:8000 |
| `siga_db` | PostgreSQL 16 de SIGA | Interna: `siga_db:5432` |
| `moodle` | Moodle 5.3 | http://localhost:8080 |
| `moodle_db` | PostgreSQL 17 de Moodle | Interna: `moodle_db:5432` |

Las bases de datos tienen credenciales y volúmenes independientes y no publican puertos en la PC. El código Django se monta desde `./src`; los documentos se guardan en un volumen privado.

## Instalación nueva

Requisitos: Docker Desktop iniciado, con contenedores Linux y Docker Compose. Los comandos siguientes usan PowerShell.

1. Abrir una terminal en esta carpeta. **Sólo si todavía no existe `.env`**, copiar la plantilla:

   ```powershell
   Copy-Item .env.example .env
   ```

2. Editar `.env`: cambiar `DJANGO_SECRET_KEY`, las dos contraseñas de PostgreSQL y `MOODLE_ADMIN_PASSWORD`; completar `MOODLE_ADMIN_EMAIL` y la cuenta de correo de SIGA. Dejar `MOODLE_API_TOKEN` vacío hasta configurar el servicio web. Las contraseñas de la plantilla son ejemplos. Si una clave contiene `$` o `#`, usar comillas simples en `.env` para conservar su valor literal.
3. Validar y levantar los cuatro servicios:

   ```powershell
   docker compose config --quiet
   docker compose up -d --build
   docker compose ps
   docker compose logs -f moodle
   ```

   La instalación inicial de Moodle puede tardar varios minutos. Esperar a que http://localhost:8080 muestre la pantalla de acceso. `Ctrl+C` deja de seguir los registros y mantiene los contenedores encendidos. SIGA aplica sus migraciones automáticamente al iniciar `web` y puede arrancar antes de que Moodle termine de instalarse.
4. Crear el administrador de Django:

   ```powershell
   docker compose exec web python manage.py createsuperuser
   ```

   Entrar en http://localhost:8000/admin/, cargar carreras, planes, períodos y cupos; para acceso a secretaría, agregar el usuario al grupo **Administrativo**.
5. Opcionalmente, para una instalación de demostración vacía:

   ```powershell
   docker compose exec web python manage.py cargar_demo
   ```

   El comando prepara datos de ejemplo y el usuario `secretaria`, con contraseña de demo `siga1234` (personalizable con `cargar_demo --password ...`). No hace falta ejecutarlo para conservar datos existentes.
6. Configurar Moodle siguiendo los pasos de la sección siguiente. El administrador de Moodle y el de Django son cuentas distintas.

## Configurar Moodle para el alta automática

### 1. Entrar como administrador y habilitar REST

1. Abrir http://localhost:8080 e ingresar con `MOODLE_ADMIN_USER` y `MOODLE_ADMIN_PASSWORD` del `.env` utilizado en la **primera instalación**. Completar los datos iniciales que solicite Moodle.
2. Ir a **Administración del sitio → Características avanzadas**, activar **Habilitar servicios web** y guardar.
3. Ir a **Administración del sitio → Servidor → Servicios web → Gestionar protocolos** y habilitar **REST**. En algunas versiones el menú aparece en **Plugins → Servicios web**; se puede buscar “Gestionar protocolos” en el buscador de administración.

Las variables `MOODLE_ADMIN_*` inicializan una instalación vacía. Cambiarlas no restablece la contraseña de un administrador ya creado.

### 2. Crear una cuenta técnica para SIGA

1. Ir a **Administración del sitio → Usuarios → Cuentas → Agregar un usuario**.
2. Crear, por ejemplo, el usuario `siga_api`, con autenticación **Cuentas manuales**, contraseña propia, nombre, apellido y correo válidos.
3. Dejar la cuenta activa, confirmada y sin suspensión. No activar “Forzar cambio de contraseña” para esta cuenta técnica. Guardar.

Esta cuenta identifica a SIGA ante la API. Es distinta del administrador y de los aspirantes que se van a crear.

### 3. Crear y asignar el rol del webservice

1. Ir a **Administración del sitio → Usuarios → Permisos → Definir roles → Agregar un nuevo rol**.
2. Continuar sin un arquetipo de rol predefinido. Usar nombre **SIGA API** y nombre corto `siga_api`.
3. En **Tipos de contexto en que puede asignarse este rol**, seleccionar **Sistema**.
4. Buscar por el identificador del permiso y seleccionar **Permitir** para estos dos:

   | Permiso | Uso |
   |---|---|
   | `webservice/rest:use` | Permite que la cuenta utilice REST |
   | `moodle/user:create` | Permite crear usuarios en el sistema |

5. Guardar el rol.
6. Ir a **Administración del sitio → Usuarios → Permisos → Asignar roles del sistema**. Abrir **SIGA API**, seleccionar `siga_api` y agregarlo.

Crear el rol no alcanza: hay que asignarlo al usuario del token en **Sistema**. Estos permisos pertenecen al rol específico de la integración, no al rol general “Usuario autenticado”.

### 4. Crear el servicio externo y autorizar al usuario

1. Ir a **Administración del sitio → Servidor → Servicios web → Servicios externos**.
2. Agregar un servicio personalizado llamado **siga**. Marcar **Habilitado** y **Sólo usuarios autorizados**. El campo de capacidad adicional requerida puede quedar vacío.
3. Abrir **Funciones → Agregar funciones** y agregar **`core_user_create_users`**.
4. Para utilizar la comprobación de sólo lectura de abajo, agregar también **`core_webservice_get_site_info`**. Esta segunda función sirve para diagnóstico y no es necesaria para crear cuentas.
5. Volver al servicio, abrir **Usuarios autorizados** y agregar `siga_api`. Comprobar que Moodle no liste permisos faltantes para ese usuario.
6. Para las pruebas locales, dejar vacía la restricción de IP. Si se configura una restricción o vencimiento, debe permitir la IP de origen que recibe Moodle desde Docker y mantenerse vigente.

El alta actual no utiliza `enrol_manual_enrol_users`: crea la cuenta, pero **no matricula automáticamente en cursos**. Esa función y los permisos de matriculación no son necesarios para este flujo.

### 5. Crear el token y cargarlo en SIGA

1. Ir a **Administración del sitio → Servidor → Servicios web → Gestionar tokens**.
2. Agregar un token seleccionando el usuario **`siga_api`** y el servicio **`siga`**. Mantener vigente su fecha de validez y revisar cualquier restricción de IP.
3. Copiar el token en `.env`, sin publicarlo ni guardarlo en el código:

   ```dotenv
   MOODLE_URL=http://moodle:8080
   MOODLE_HOST_HEADER=localhost:8080
   MOODLE_API_TOKEN=pegar_aqui_el_token_del_servicio_siga
   ```

4. Recrear únicamente Django para que tome las variables nuevas:

   ```powershell
   docker compose up -d --no-deps --force-recreate web
   ```

`docker compose restart web` no vuelve a cargar el `.env`. Si el token, el usuario y el servicio ya están configurados y se conservaron los volúmenes de Moodle, se puede reutilizar el mismo token.

### 6. Comprobar la conexión sin crear usuarios

Con `core_webservice_get_site_info` agregado al servicio, ejecutar desde PowerShell:

```powershell
@'
import json
import os
from urllib.parse import urlencode
from urllib.request import Request, urlopen

datos = urlencode({
    "wstoken": os.environ["MOODLE_API_TOKEN"],
    "wsfunction": "core_webservice_get_site_info",
    "moodlewsrestformat": "json",
}).encode()
solicitud = Request(
    os.environ["MOODLE_URL"].rstrip("/") + "/webservice/rest/server.php",
    data=datos,
    headers={"Host": os.environ.get("MOODLE_HOST_HEADER", "localhost:8080")},
)
with urlopen(solicitud, timeout=10) as respuesta:
    resultado = json.load(respuesta)
if resultado.get("exception"):
    print(resultado.get("errorcode"), resultado.get("message"))
else:
    funciones = {f["name"] for f in resultado.get("functions", [])}
    print("Conexion y token: OK")
    print("Funcion de alta disponible:", "core_user_create_users" in funciones)
'@ | docker compose exec -T web python -B -
```

La salida esperada es `Conexion y token: OK` y `Funcion de alta disponible: True`. No se imprime el token ni se crea una cuenta. Si la función de consulta no se agregó al servicio, esta comprobación puede devolver un error de acceso aunque el alta esté habilitada.

### 7. Comprobar el circuito de aceptación

1. Cargar una preinscripción de prueba desde http://localhost:8000/preinscripcion/ con un DNI que no exista en Moodle y un correo de prueba al que se tenga acceso.
2. Entrar en http://localhost:8000/administracion/ como usuario del grupo **Administrativo** y aceptar la solicitud.
3. Comprobar en **Moodle → Usuarios → Cuentas → Examinar lista de usuarios** que se creó la cuenta con el DNI como nombre de usuario.
4. Revisar el correo de aceptación: incluye usuario y clave temporal. Al ingresar por primera vez, Moodle debe solicitar cambiar la clave. Si el correo de SIGA está en modo consola, revisar `docker compose logs web`.

SIGA guarda el ID de Moodle en la persona. Si esa misma persona vuelve a ser aceptada por otra postulación y ya tiene un ID vinculado, reutiliza la cuenta y no genera otra contraseña. Si Moodle rechaza el alta o no responde, la solicitud permanece pendiente. Una cuenta creada previamente de forma manual en Moodle, pero sin ID vinculado en SIGA, no se vincula automáticamente por DNI o correo.

## Cómo se llama a la API

El endpoint REST usado por Django es:

```text
POST http://moodle:8080/webservice/rest/server.php
Host: localhost:8080
Content-Type: application/x-www-form-urlencoded
```

El cuerpo lleva `wstoken`, `wsfunction=core_user_create_users`, `moodlewsrestformat=json` y los campos `users[0][username]`, `password`, `firstname`, `lastname`, `email`, `auth=manual`, `idnumber` y la preferencia `auth_forcepasswordchange=1`.

| Variable | Significado local |
|---|---|
| `SITE_URL` | Dirección pública de SIGA para enlaces en sus correos: `http://localhost:8000` |
| `MOODLE_SITE_URL` | Dirección pública de Moodle y su `wwwroot`: `http://localhost:8080` |
| `MOODLE_URL` | Dirección interna de Moodle vista desde Django: `http://moodle:8080` |
| `MOODLE_HOST_HEADER` | Host canónico de Moodle, incluyendo puerto: `localhost:8080` |

Desde Windows o Postman se utiliza `http://localhost:8080/webservice/rest/server.php`. Dentro de Docker, `localhost` identifica al propio contenedor; por eso Django usa el nombre de servicio `moodle`. No hay que agregar `/webservice/rest/server.php` a `MOODLE_URL`: el código ya agrega esa ruta.

La configuración local de Moodle usa el puerto 8080 tanto fuera como dentro del contenedor. Cambiar únicamente el puerto publicado puede provocar redirecciones: Moodle también comprueba el puerto recibido por PHP. Para usar otro puerto o un proxy, revisar la configuración del servidor de la imagen, la dirección pública y `MOODLE_HOST_HEADER` en conjunto. En una instalación existente, verificar además el `$CFG->wwwroot` guardado en `config.php`: cambiar una variable inicial no garantiza modificar esa configuración persistida.

## Reutilizar los datos de SIGA - copia y del Moodle anterior

Esta transición usa los datos existentes, no una instalación vacía. Antes de iniciar el Compose unificado:

1. Detener los contenedores de los dos proyectos anteriores. Si todavía existen con sus nombres originales:

   ```powershell
   docker stop siga-copia-web-1 siga-copia-db-1 moodle_app moodle_db
   ```

2. Con los contenedores detenidos, respaldar los cinco volúmenes desde Docker Desktop y comprobar sus nombres con `docker volume ls`. No ejecutar dos PostgreSQL sobre el mismo volumen.
3. Conservar las credenciales de PostgreSQL con las que se inicializó cada base y el token ya configurado en Moodle. El `.env` local de esta unificación se preparó con esas credenciales, el token de la copia y estos volúmenes:

   ```dotenv
   EXTERNAL_DATA_VOLUMES=true
   SIGA_DB_VOLUME=siga-copia_pgdata
   SIGA_MEDIA_VOLUME=siga-copia_media
   MOODLE_DB_VOLUME=moodle_pgdata
   MOODLE_DATA_VOLUME=moodle_moodledata
   MOODLE_HTML_VOLUME=moodle_moodlehtml
   ```

   Verificar los nombres si se realiza la transición en otra PC. `external=true` exige que los volúmenes ya existan y evita que Compose los cree vacíos o los elimine al quitar el proyecto. La plantilla `.env.example`, en cambio, usa nombres nuevos y `external=false`.
4. Ejecutar desde **SIGA**:

   ```powershell
   docker compose config --quiet
   docker compose up -d --build
   docker compose ps
   ```

5. Revisar el acceso a ambos sistemas, las solicitudes y los archivos. La migración `core.0002_persona_moodle_user_id` se aplica automáticamente si falta; si ya se aplicó en la base de la copia, Django la conserva como aplicada.

El nuevo proyecto Compose se llama `siga` y genera sus propios nombres de contenedor, sin chocar con los contenedores anteriores detenidos. El servicio `moodle_db` conserva el alias interno `db` para que siga funcionando el `config.php` del Moodle anterior. No se sobrescribe ese archivo persistido. Los arranques siguientes se hacen desde **SIGA**; `SIGA - copia` deja de ser necesaria para ejecutar el sistema. `_docker-compose.yml` es un archivo anterior y no se usa en estos comandos.

## Correo

SIGA envía tres correos: recepción, aceptación y rechazo con motivo. Mantiene una versión HTML y otra de texto plano. Las plantillas comparten el diseño de `src/templates/emails/base.html`.

Sin `EMAIL_HOST_PASSWORD`, se usa la consola. Para enviar por Gmail:

1. Activar la verificación en dos pasos y generar una **contraseña de aplicación** en la cuenta de Google del proyecto.
2. Completar `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD` y `DEFAULT_FROM_EMAIL` en `.env`.
3. Ejecutar `docker compose up -d --no-deps --force-recreate web`.
4. Probar con `docker compose exec web python manage.py probar_correo tu@correo.com`.

Esta configuración corresponde a los correos enviados por SIGA. El correo propio de Moodle se configura por separado en Moodle si se necesita, por ejemplo, para recuperar contraseñas. `.env` está excluido de Git y no debe compartirse con tokens ni claves.

## Problemas frecuentes

| Síntoma | Qué revisar |
|---|---|
| `Connection refused` | Moodle todavía está iniciando o `MOODLE_URL` apunta a `localhost` dentro de Django. Usar `http://moodle:8080`. |
| `accessexception` | REST y servicios web habilitados; servicio activo; usuario autorizado, activo y con el rol asignado en Sistema; permiso `webservice/rest:use`; función solicitada agregada al servicio; restricciones de IP y vencimiento. |
| Falta `moodle/user:create` | Permitir ese permiso en el rol de la cuenta técnica y comprobar su asignación en Sistema. |
| `invalidtoken` | Token copiado sin espacios, vigente y perteneciente al servicio correcto. Recrear `web` después de editar `.env`. |
| Respuesta HTML, redirección o dirección incorrecta | `MOODLE_HOST_HEADER` debe coincidir con el host de `wwwroot`; revisar `MOODLE_SITE_URL` y el `config.php` persistido. |
| Usuario o correo ya existente | La cuenta no está vinculada a la persona de SIGA. Resolver esa vinculación antes de reintentar; el flujo actual no busca ni adopta cuentas existentes por correo. |
| PostgreSQL rechaza la contraseña | Las variables deben coincidir con las usadas al inicializar el volumen. Editar `.env` no cambia la contraseña de una base ya creada. |
| `external volume ... not found` | Revisar los nombres de los volúmenes anteriores. Para una instalación nueva usar los nombres de la plantilla y `EXTERNAL_DATA_VOLUMES=false`. |
| Puerto 8000 u 8080 ocupado | Detener los contenedores anteriores. Si se cambia el puerto de Moodle, revisar también la configuración del servidor y `wwwroot` como se explica arriba. |

## Comandos útiles

```powershell
docker compose up -d --build
docker compose ps
docker compose logs -f web moodle
docker compose exec web python manage.py check
docker compose exec web python manage.py test
docker compose exec web python manage.py showmigrations core
docker compose exec web python manage.py makemigrations --check --dry-run
docker compose stop
docker compose down
```

`stop` y `down` conservan los datos. No agregar `--volumes` / `-v` al apagar: en instalaciones nuevas eliminaría las bases y los archivos administrados por Compose. El servidor Django incluido es para desarrollo local.

## Estructura y reglas

```text
docker-compose.yml   web + siga_db + moodle + moodle_db
Dockerfile           Python 3.12 y dependencias de Django
src/
├─ config/           configuración y URLs
├─ templates/        plantillas base, login y correos
├─ static/           CSS, JS e íconos
└─ apps/
   ├─ core/            personas, carreras, planes, períodos y cupos
   ├─ admisiones/      preinscripciones, correos e integración REST con Moodle
   ├─ preinscripcion/  formulario público
   └─ administracion/  bandeja, ficha y aceptación/rechazo
```

Las dependencias van en un solo sentido: `core` ← `admisiones` ← `preinscripcion` / `administracion`. Ninguna app importa desde `preinscripcion`.

| Tabla | Contenido |
|---|---|
| `personas` | Persona única por DNI y `moodle_user_id` opcional, único cuando está definido |
| `carreras`, `planes_carreras` | Oferta académica |
| `periodos_inscripcion` | Ventana de fechas |
| `periodos_inscripcion_planes` | Planes ofrecidos y cupos |
| `preinscripciones` | Estado, responsable y fecha de resolución |
| `documentos_preinscripciones` | DNI, título o constancia, y analítico opcional |

Una persona tiene una sola solicitud activa por período; las rechazadas no cuentan. Los cupos incluyen solicitudes pendientes y aceptadas. Los documentos se guardan con nombres aleatorios y se sirven únicamente desde una vista con control de acceso.

Referencias: [servicios web de Moodle](https://docs.moodle.org/503/en/Using_web_services), [roles personalizados](https://docs.moodle.org/503/en/Creating_custom_roles), [protocolo REST y parámetros](https://supportus.moodle.com/support/solutions/articles/80001016973-using-the-web-services-application-programming-interface-api-in-moodle), [imagen alpine-moodle](https://github.com/erseco/alpine-moodle).
