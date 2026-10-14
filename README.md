# SIGA · Sistema Integral de Gestión Académica

Instituto Técnico Superior N.º 1 (Viedma, Río Negro). Primera etapa: **circuito de ingreso**.

- **Formulario público de preinscripción** (`/preinscripcion/`): el aspirante carga sus datos, elige la carrera y adjunta la documentación. No necesita una cuenta.
- **Bandeja de aspirantes** (`/administracion/`): secretaría ve las solicitudes del período, con filtros y cupos por carrera.
- **Ficha del aspirante** (`/administracion/aspirantes/<id>/`): datos, documentación y resolución. La solicitud se **acepta o rechaza completa**. Si se rechaza, el aspirante recibe el motivo por correo y vuelve a completar el formulario.

La documentación del proyecto está en [`docs/`](docs/).

## Puesta en marcha

Requisitos: Docker Desktop (o Docker Engine con Compose).

```bash
cp .env.example .env
docker compose up -d --build
docker compose exec web python manage.py cargar_demo
```

- Formulario: http://localhost:8000/preinscripcion/
- Panel de secretaría: http://localhost:8000/administracion/ — usuario `secretaria`, contraseña `siga1234` (sólo datos de demo; se cambia con `cargar_demo --password ...`)
- Admin de Django (carreras, planes, períodos y cupos): http://localhost:8000/admin/ — crear un superusuario con `docker compose exec web python manage.py createsuperuser`

### Correo

SIGA envía tres correos al aspirante: al recibir la solicitud, al aceptarla y al rechazarla (con el motivo).

Los tres incluyen una versión HTML con el diseño compartido de `src/templates/emails/base.html` y una alternativa de texto plano. Cada estado tiene su propia plantilla; los estilos principales están en línea para compatibilidad con clientes de correo.

Mientras `EMAIL_HOST_PASSWORD` esté vacío en `.env`, **no se envían**: se imprimen en la consola.

```bash
docker compose logs -f web
```

Para enviarlos por la cuenta de Gmail del proyecto (`siga_dev.its@gmail.com`):

1. En la cuenta de Google, activar la verificación en dos pasos y crear una **contraseña de aplicación** (Cuenta de Google → Seguridad → Contraseñas de aplicaciones). Es un código de 16 letras; no es la contraseña normal de la cuenta.
2. Pegarla en `.env` en `EMAIL_HOST_PASSWORD=`, sin espacios.
3. Reiniciar el contenedor para que tome el cambio: `docker compose up -d`
4. Probar: `docker compose exec web python manage.py probar_correo tu@correo.com`

El `.env` no se sube al repositorio, así que la contraseña queda sólo en cada máquina.

### Comandos útiles

```bash
docker compose exec web python manage.py test            # tests
docker compose exec web python manage.py makemigrations  # después de cambiar un modelo
docker compose down                                      # apagar (los datos quedan)
docker compose down -v                                   # apagar y BORRAR base y archivos
```

El código está en `src/` y está montado dentro del contenedor: se edita con VS Code y Django recarga solo.

## Estructura

```
docker-compose.yml   web (Django) + db (PostgreSQL 16)
Dockerfile           imagen de Python con las dependencias
src/
├─ config/           settings y URLs
├─ templates/        plantillas base, login y correos
├─ static/           CSS, JS e íconos (Lucide)
└─ apps/
   ├─ core/            datos compartidos: personas, carreras, planes, períodos y cupos
   ├─ admisiones/      preinscripciones, documentos, cupos y correos
   ├─ preinscripcion/  formulario público (app desmontable)
   └─ administracion/  rol administrativo: bandeja, ficha, aceptar/rechazar
```

**Una app por rol**, más las apps de dominio. Las dependencias van en un solo sentido: `core` ← `admisiones` ← `preinscripcion` / `administracion`. **Nadie importa de `preinscripcion`**: si se saca de `INSTALLED_APPS`, el formulario deja de existir y el panel sigue funcionando.

## Modelo de datos de esta etapa

| Tabla | Para qué |
|---|---|
| `personas` | Datos de la persona (único por DNI). Hoy aspirantes; mañana estudiantes y docentes. |
| `carreras`, `planes_carreras` | Oferta académica. |
| `periodos_inscripcion` | Ventana de fechas de la inscripción. |
| `periodos_inscripcion_planes` | Qué plan se ofrece en el período y con qué cupo. |
| `preinscripciones` | La solicitud: `pendiente`, `aceptado` o `rechazado`, quién la resolvió y cuándo. |
| `documentos_preinscripciones` | Archivos adjuntos: DNI, título **o** constancia en trámite, analítico (opcional). |

Reglas principales:

- Una persona tiene **una sola solicitud activa por período**. Las rechazadas no cuentan, así puede volver a enviar.
- El cupo cuenta las solicitudes pendientes y aceptadas. Una carrera sin cupo aparece en el formulario, pero **deshabilitada**.
- Los archivos se guardan con un nombre aleatorio en un volumen privado y **no tienen URL pública**: se ven sólo desde la ficha, con el rol administrativo.
- Roles: grupo de Django **Administrativo** (lo crea una migración). Para dar acceso a una persona, se la agrega a ese grupo desde el admin.
