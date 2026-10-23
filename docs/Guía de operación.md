# Guía de operación — Moodle Course as Code

Instalación, credenciales, ciclo de vida de releases y resolución de
incidencias del servicio `courseascode`. Complementa la
[especificación](Especificación%20Moodle%20Course%20as%20Code%20v0.2.md).

## Componentes

| Pieza | Qué es | Dónde |
|---|---|---|
| Engine (`courseascode`) | Servicio Python: preview, catálogo, despliegue, releases | este repo (`engine/`) |
| Plugin `local_courseascode` 🔌 | Tabla, web services y páginas en Moodle | pista paralela (no en este repo) |
| Repo de contenidos | Git con `course.yml`, `books/<id>/book.yml` y Markdown | vuestro Git (GitHub/GitLab…) |

El engine habla con Moodle solo a través de los web services del plugin
(`local_courseascode_*`, contrato en `engine/src/courseascode/moodle/functions.py`).

## Credenciales y tokens

| Credencial | Dónde se configura | Uso |
|---|---|---|
| Cuenta técnica Moodle + token | `MOODLE_URL` + `MOODLE_TOKEN` | web services del plugin (capabilities mínimas, §5.3d) |
| Token de coordinador | `COURSEASCODE_ADMIN_TOKEN` | `courseascode release mark` y `GET /audit` (rol coordinador) |
| Secreto del webhook | `COURSEASCODE_WEBHOOK_SECRET` | firma HMAC de `POST /hooks/git` (header `X-CourseAsCode-Signature: sha256=<hex>`) |

Las credenciales viven **solo** en variables de entorno (§25); nunca en el repo.

## Despliegue del servicio

Con Docker (desde la raíz del repo):

```bash
docker compose up --build     # engine :8000 + Moodle :8080 + MariaDB
```

Sin Docker:

```bash
cd engine && pip install .
CONTENT_REPO=/ruta/al/repo-de-contenidos \
MOODLE_URL=… MOODLE_TOKEN=… \
python -m courseascode.serve          # uvicorn, HOST/PORT configurables
```

Variables: ver la tabla del `engine/README.md`. Logs en JSON en producción
(`COURSEASCODE_LOG_FORMAT=json`); cada operación lleva **correlation id**
(header `X-Correlation-Id` en la API, campo en cada evento) para cruzar
CLI ↔ API ↔ Moodle.

## Backup

La fuente de verdad del **contenido** es Git. La del **binding
curso↔versión** es la tabla del plugin en Moodle (backup estándar). La BD
SQLite del engine (`COURSEASCODE_DB`: releases, severidades, recalls y
auditoría) se backupea copiando el fichero con el servicio parado:

```bash
cp ~/.courseascode/courseascode.db /backup/courseascode-$(date +%F).db
```

## Ciclo de vida de releases (§11)

```text
DRAFT → RELEASED → SUPERSEDED → (opcional) RECALLED
```

- Solo versiones taggeadas son importables/desplegables.
- **RECALLED**: bloqueada para nuevos despliegues; los cursos que ya la tienen
  reciben aviso crítico pero **no se les cambia nada automáticamente**.

```bash
# El coordinador declara severidad/recall (motivo obligatorio si critical/recall):
courseascode release mark book/ut03-mvc/v1.3.0 \
  --severity critical --fixed-in v1.3.1 \
  --reason "El ejemplo del patrón Active Record contenía SQL inseguro"

courseascode release list ut03-mvc          # estado del ciclo de vida
```

**Flujo de hotfix (§11.1):** forward-fix siempre — se publica un PATCH con solo
la corrección, se marca la versión afectada (comando anterior) y el sistema
calcula los cursos afectados (`GET /releases/affected`); la notificación a
profesores la envía el plugin 🔌. Nuevos despliegues de una versión RECALLED
fallan; `--force` los salta y queda **avisado en el resultado y en auditoría**.

## Troubleshooting

| Síntoma | Causa probable | Acción |
|---|---|---|
| `ERROR` en `status` | el último deploy falló a mitad | **Relanza el mismo deploy**: el pipeline es idempotente y continúa donde falló (mensaje de error accionable) |
| `DRIFT_DETECTED` | alguien editó el Book a mano en Moodle | Redeploy de la misma versión: sobrescribe el drift |
| Deploy bloqueado "RECALLED" | versión retirada | Actualiza a la versión que corrige (`--fixed-in`); solo usa `--force` en casos excepcionales |
| Webhook no llega / 401 | secreto o firma | `COURSEASCODE_WEBHOOK_SECRET` definido y firma `sha256=` del body crudo; sin secreto el endpoint responde 503 |
| `GET /audit` 401 | sin token | Header `X-CourseAsCode-Admin-Token` con el token de coordinador |
| Preview lenta tras muchos tags | caché expirada (TTL 15 min) | Esperar o reiniciar; el webhook de Git invalida el caché completo |

## Límites conocidos de la Beta

- `status` exige `--course` (el provider no lista cursos globalmente).
- La identidad de llamante del catálogo (`X-CourseAsCode-User`) es provisional;
  la autenticación real llega con el plugin 🔌.
- La suite E2E de aceptación (§32) contra moodle-docker queda en mark
  `integration` hasta disponer del plugin; el fake cubre el contrato en CI.
- El plugin `local_courseascode` 🔌 (tabla, web services, páginas) es pista
  paralela: su hito crítico (tabla + `upsert_book/chapter` + token) debe estar
  listo antes de las pruebas de contrato reales (ENG-104 en Moodle real).
