# Sistema Academico Distribuido Seguro

Implementacion del proyecto: 3 microservicios independientes (Autenticacion,
Academico, Auditoria), cada uno con su propia base de datos PostgreSQL,
comunicandose por HTTP/JSON, con JWT + RBAC, bcrypt para contrasenas y
auditoria centralizada de eventos.

## Arquitectura

```
                     ┌────────────────────┐
        JWT          │  Servicio de        │
   ┌────────────────►│  Autenticacion       │  (puerto 8001)
   │                  │  usuarios / roles    │
   │                  └─────────┬────────────┘
   │                            │ crea usuario (clave interna)
   │                  ┌─────────▼────────────┐        ┌──────────────────┐
   │  cliente/front   │  Servicio Academico   │───────►│ Servicio Auditoria│ (8002)
   └─────────────────►│  alumnos/docentes/    │ eventos│  logs             │
                      │  cursos/matriculas/   │        └──────────────────┘
                      │  notas (8000)          │
                      └────────────────────────┘
```

Cada servicio tiene su propia base de datos (`auth_db`, `academic_db`,
`audit_db`). El Servicio Academico es el unico que habla con los otros dos:
cuando un Coordinador/Admin crea un docente o alumno, primero crea la cuenta
de acceso en el Servicio de Autenticacion (con clave interna compartida) y
luego el perfil academico, quedando siempre vinculados por `user_id`. Si el
segundo paso falla, revierte el primero (patron Saga simple).

## Como levantarlo

```bash
cp .env.example .env      # editar JWT_SECRET / INTERNAL_API_KEY / password admin
docker compose up --build
```

Servicios expuestos:
- Autenticacion: http://localhost:8001 (docs en /docs)
- Academico: http://localhost:8000 (docs en /docs)
- Auditoria: http://localhost:8002 (docs en /docs)

Al iniciar por primera vez, el Servicio de Autenticacion crea un usuario
ADMIN inicial con las credenciales de `ADMIN_BOOTSTRAP_EMAIL` /
`ADMIN_BOOTSTRAP_PASSWORD` (por defecto `admin@universidad.edu` /
`Admin123!`). Cambia esa contrasena apenas inicies sesion.

## Flujo tipico de uso

1. **Login admin** -> `POST /auth/login` en el servicio de autenticacion.
2. **Crear coordinador** (solo el admin puede, via `POST /auth/register`
   con header `X-Internal-Key`, o agregando un endpoint de administracion
   si lo prefieres publico).
3. **Login coordinador** -> obtiene su JWT.
4. **Coordinador crea un docente** -> `POST /courses`... perdon,
   `POST /teachers` en el Servicio Academico (crea login + perfil).
5. **Coordinador crea un alumno** -> `POST /students`.
6. **Coordinador crea un curso** -> `POST /courses`.
7. **Coordinador asigna el docente al curso** -> `POST /courses/{id}/assign-teacher`.
8. **Coordinador matricula al alumno** -> `POST /enrollments`.
9. **Docente inicia sesion** -> `POST /auth/login`.
10. **Docente registra la nota** -> `POST /grades`.
11. **Alumno inicia sesion y ve su nota** -> `GET /grades`.

Todas las acciones relevantes (login, creaciones, notas, accesos denegados)
quedan registradas en el Servicio de Auditoria, consultable via `GET /logs`,
`GET /logs/user/{id}` y `GET /logs/security` (solo Coordinador/Admin).

## Roles y permisos (resumen)

| Accion                              | Alumno | Docente | Coordinador | Admin |
|--------------------------------------|:------:|:-------:|:------------:|:-----:|
| Ver sus propios cursos/notas         |   x    |    -    |      -       |   -   |
| Ver cursos/alumnos asignados         |   -    |    x    |      -       |   -   |
| Registrar/editar notas (curso propio)|   -    |    x    |      -       |   x   |
| Crear/editar alumnos, docentes       |   -    |    -    |      x       |   x   |
| Crear/editar/asignar cursos          |   -    |    -    |      x       |   x   |
| Matricular / desmatricular           |   -    |    -    |      x       |   x   |
| Ver auditoria                        |   -    |    -    |      x       |   x   |
| Habilitar/deshabilitar usuarios      |   -    |    -    |      x       |   x   |

## Seguridad implementada

- Contrasenas con `bcrypt` (nunca en texto plano ni reversibles).
- JWT (`HS256`) con expiracion, validado de forma independiente por cada
  microservicio (comparten `JWT_SECRET`, no hay llamada de red por cada
  request).
- Bloqueo temporal de cuenta tras varios intentos fallidos de login
  (`MAX_INTENTOS_FALLIDOS`, `BLOQUEO_MINUTOS`).
- RBAC: cada endpoint exige el/los roles correctos via dependencias
  (`require_roles`).
- Los endpoints internos entre servicios (`/auth/register`, eliminacion de
  usuario, `/events` de auditoria) estan protegidos por una clave interna
  compartida (`X-Internal-Key`), no son publicos.
- Auditoria de: login (implicito por bloqueo), creacion de usuarios,
  matriculas, cursos, notas, y todos los accesos denegados.
- Validacion de entradas con Pydantic (tipos, longitudes, rangos de notas
  0-20).

## Limitaciones conocidas / siguientes pasos sugeridos

- El logout es "stateless": el JWT sigue siendo valido hasta que expira.
  Para invalidacion inmediata se necesitaria una lista negra (ej. Redis).
- No hay HTTPS configurado en docker-compose (para produccion, ponerlo
  detras de un reverse proxy con TLS, ej. Nginx/Traefik).
- No incluye frontend; los endpoints estan listos para conectarse desde
  cualquier cliente (React, etc.) usando el JWT en `Authorization: Bearer`.
- La compensacion Saga entre Academico y Autenticacion es "best effort"
  (no hay reintentos ni cola de mensajes); para un entorno productivo
  conviene un bus de eventos (RabbitMQ/Kafka) con reintentos.
