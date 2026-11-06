# SIGA · Sistema Integral de Gestión Académica

Instituto Técnico Superior N.º 1 (Viedma, Río Negro). Primera etapa: **circuito de ingreso**.

- **Formulario público** (`/preinscripcion/`): el aspirante carga sus datos, elige la carrera y adjunta la documentación sin necesitar una cuenta.
- **Bandeja de aspirantes** (`/administracion/`): secretaría consulta solicitudes, filtros, cupos y descarga el **listado de inscriptos aprobados en formato PDF** (`/administracion/aprobados/pdf/`).
- **Ficha** (`/administracion/aspirantes/<id>/`): permite aceptar o rechazar la solicitud completa. Al aceptar, SIGA crea o vincula la cuenta en Moodle mediante su API REST y envía las credenciales por correo. Al rechazar, envía el motivo para que el aspirante vuelva a completar el formulario.

La documentación del dominio está en [`docs/`](docs/).

## Servicios propios en Docker Compose

El archivo `docker-compose.yml`, ejecutado desde esta carpeta **SIGA**, levanta los dos servicios propios del sistema:

| Servicio | Función | Dirección |
|---|---|---|
| `web` | Aplicación Django / SIGA | http://localhost:8000 |
| `siga_db` | PostgreSQL 16 de SIGA | Interna: `siga_db:5432` |

La base de datos persiste en el volumen `siga_pgdata` y no publica puertos en la PC. El código Django se monta desde `./src`; los documentos adjuntos se guardan en el volumen privado `siga_media` fuera de rutas públicas. Moodle y el servidor SMTP operan como servicios externos independientes con los que SIGA se comunica por red.

## Instalación y puesta en marcha

Requisitos: Docker Desktop iniciado, con contenedores Linux y Docker Compose. Los comandos siguientes usan PowerShell.

1. Abrir una terminal en esta carpeta. **Sólo si todavía no existe `.env`**, copiar la plantilla:

   ```powershell
   Copy-Item .env.example .env
   ```

2. Editar `.env`: configurar `DJANGO_SECRET_KEY`, `POSTGRES_PASSWORD` y la cuenta de correo SMTP de SIGA. La integración con Moodle viene desactivada por defecto (`MOODLE_ACTIVO=0`) para poder probar todo el aplicativo sin depender de un servidor Moodle externo; para activarla, cambiar a `MOODLE_ACTIVO=1` y completar `MOODLE_URL`, `MOODLE_HOST_HEADER` y `MOODLE_API_TOKEN`.
3. Validar y levantar los dos servicios de SIGA:

   ```powershell
   docker compose config --quiet
   docker compose up -d --build
   docker compose ps
   ```

   SIGA aplica sus migraciones automáticamente al iniciar `web`.
4. Crear el administrador de Django:

   ```powershell
   docker compose exec web python manage.py createsuperuser
   ```

   Entrar en http://localhost:8000/admin/, cargar carreras, planes, períodos y cupos; para acceso a secretaría, agregar el usuario al grupo **Administrativo**.
5. Opcionalmente, para cargar datos iniciales de demostración:

   ```powershell
   docker compose exec web python manage.py cargar_demo
   ```

   El comando prepara el período activo, las cinco carreras del ITS N.º 1 con sus cupos y el usuario `secretaria` con contraseña `siga1234` (personalizable con `cargar_demo --password ...`).

## Exportación de inscriptos aprobados en PDF (Extensión 1)

Desde la bandeja administrativa (`/administracion/`), el botón **Listado de aprobados (PDF)** genera y descarga un documento PDF en tamaño A4 (`/administracion/aprobados/pdf/`) con los aspirantes en estado **Aceptado** del período actual, agrupados por carrera e incluyendo número de trámite (`PRE-AAAA-NNNNN`), DNI, apellido y nombre, correo electrónico, teléfono y fecha de aceptación. Si la bandeja tiene aplicado el filtro por carrera, el PDF exporta únicamente la nómina de esa carrera.

## Configurar el servidor Moodle externo para el alta automática (Extensión 3)

### 1. Entrar como administrador en Moodle y habilitar REST

1. Ingresar al servidor Moodle con cuenta de administrador.
2. Ir a **Administración del sitio → Características avanzadas**, activar **Habilitar servicios web** y guardar.
3. Ir a **Administración del sitio → Servidor → Servicios web → Gestionar protocolos** y habilitar **REST**.

### 2. Crear una cuenta técnica para SIGA

1. Ir a **Administración del sitio → Usuarios → Cuentas → Agregar un usuario**.
2. Crear el usuario `siga_api`, con autenticación **Cuentas manuales**, contraseña propia, nombre, apellido y correo válidos.
3. Dejar la cuenta activa, confirmada y sin forzar cambio de contraseña.

### 3. Crear y asignar el rol del webservice

1. Ir a **Administración del sitio → Usuarios → Permisos → Definir roles → Agregar un nuevo rol**.
2. Usar nombre **SIGA API** y nombre corto `siga_api`, asignable en el contexto **Sistema**.
3. Permitir los siguientes cuatro permisos:

   | Permiso en el panel | Identificador | Uso |
   |---|---|---|
   | Usar protocolo REST | `webservice/rest:use` | Permite que la cuenta utilice REST |
   | Crear usuarios | `moodle/user:create` | Crea la cuenta del aspirante |
   | Ver perfiles de usuario | `moodle/user:viewdetails` | Permite encontrar cuentas existentes por DNI |
   | Actualizar perfiles de usuario | `moodle/user:update` | Permite restablecer la clave |

4. En **Administración del sitio → Usuarios → Permisos → Asignar roles del sistema**, asignar el rol **SIGA API** al usuario `siga_api`.

### 4. Crear el servicio externo y el token

1. En **Administración del sitio → Servidor → Servicios web → Servicios externos**, agregar un servicio personalizado llamado **siga** (**Habilitado** y **Sólo usuarios autorizados**).
2. Agregar las funciones `core_user_get_users_by_field`, `core_user_create_users`, `core_user_update_users` y `core_webservice_get_site_info`, y autorizar al usuario `siga_api`.
3. En **Gestionar tokens**, crear un token para `siga_api` en el servicio `siga`, pegarlo en `MOODLE_API_TOKEN` dentro de `.env` y recrear el contenedor `web`:

   ```powershell
   docker compose up -d --no-deps --force-recreate web
   ```

## Correo (Extensión 2)

SIGA envía tres correos multipart (texto plano y HTML): recepción, aceptación y rechazo con motivo. Sin `EMAIL_HOST_PASSWORD`, los correos se imprimen en la consola del contenedor `web`. Para enviar por Gmail, configurar una contraseña de aplicación en `EMAIL_HOST_PASSWORD` y probar con:

```powershell
docker compose exec web python manage.py probar_correo tu@correo.com
```

## Reconciliar cuentas de Moodle

Si una solicitud quedó aceptada pero la persona no tiene `moodle_user_id`, el comando busca la cuenta por DNI y la vincula:

```powershell
docker compose exec web python manage.py reconciliar_moodle --dry-run
docker compose exec web python manage.py reconciliar_moodle
```

## Comandos útiles

```powershell
docker compose up -d --build
docker compose ps
docker compose logs -f web
docker compose exec web python manage.py check
docker compose exec web python manage.py test
docker compose exec web python manage.py makemigrations --check --dry-run
docker compose exec web python manage.py reconciliar_moodle --dry-run
docker compose stop
docker compose down
```

## Estructura y reglas

```text
docker-compose.yml   web + siga_db
Dockerfile           Python 3.12 y dependencias de Django
src/
├─ config/           configuración y URLs
├─ templates/        plantillas base, login y correos
├─ static/           CSS, JS, fuentes e íconos locales
└─ apps/
   ├─ core/            personas, carreras, planes, períodos y probar_correo
   ├─ admisiones/      preinscripciones, cupos, servicios, correos y cliente REST Moodle
   ├─ preinscripcion/  formulario público (desmontable)
   └─ administracion/  bandeja, ficha, exportación PDF de aprobados y permisos
```

Las dependencias van en un solo sentido: `core` ← `admisiones` ← `preinscripcion` / `administracion`. Ninguna app importa desde `preinscripcion`.
