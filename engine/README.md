# courseascode-engine

Motor Python de **Moodle Course as Code**: un único renderer sirve la preview
web, el catálogo y el despliegue idempotente de Books versionados en Git hacia
Moodle. Ver el [README del repositorio](../../README.md) y la
[especificación](../../docs/Especificación%20Moodle%20Course%20as%20Code%20v0.2.md).

## Arquitectura

| Módulo | Responsabilidad |
|---|---|
| `domain/` | Modelos puros (SemVer, ContentId, DeploymentPlan/State…). No importa de nadie. |
| `manifests/` | Esquemas y validación de `course.yml`/`book.yml` (§20). |
| `git/` | Abstracción Git (worktrees aislados, diff, resolución de versiones por tags). |
| `content/` | Renderer único (§14): Markdown → HTML sanitizado, temas, resolvers de enlaces/assets, caché de renders. |
| `catalog/` | Catálogo derivado del último tag de cada Book (nunca HEAD) + `SourceRegistry` con ACL. |
| `moodle/` | `MoodleProvider` (REST sobre web services) + `FakeMoodleProvider` para tests; contrato del plugin en `functions.py`. |
| `deployment/` | `Planner` (diff vs Moodle), `Executor` (idempotente, dos pasadas de assets), pipeline §17, estados (§19), export. |
| `releases/` | Persistencia SQLite (SQLModel) de releases y auditoría; `SqlReleasePort`. |
| `api/` | Routers: deployment, releases/afectados, webhook de Git. |
| `web/` | App FastAPI: preview + catálogo + endpoints públicos. |
| `cli/` | Comandos Typer (§29). |

## Desarrollo

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e .[dev]
make check              # ruff + ruff format + mypy --strict + pytest
make test-integration   # suite E2E contra moodle-docker (skip sin credenciales)
```

## CLI

```text
courseascode validate [path] [--ref]        # valida manifests, capítulos, assets, enlaces
courseascode preview <book> [--ref] [--port 3000]
courseascode info <book>                    # metadata, capítulos, assets, commit, tags
courseascode build <book>                   # render a disco (build/<id>/) sin desplegar
courseascode deploy --course C --book B [--version V | --ref R] [--yes] [--force]
courseascode status --course C              # estado por Book (§19)
courseascode export --course C              # deployments/<curso>.yml (vista exportable, §9)
courseascode release mark <ref> --severity critical --recall --fixed-in V --reason R
courseascode release list <book>
```

## Servicio web

```bash
CONTENT_REPO=/ruta/al/repo-de-contenidos \
MOODLE_URL=https://moodle.example MOODLE_TOKEN=… \
python -m courseascode.serve               # uvicorn en 0.0.0.0:8000 (HOST/PORT)
```

Endpoints principales: `/` (índice de books), `/books/{id}/{capítulo}`,
`/catalog`, `/catalog/{fuente}/{book}/versions`, `/catalog/{fuente}/{book}/preview?ref=`,
`POST /deploy`, `POST /deployment/plan`, `GET /deployment/status`, `GET /deployment/where`,
`GET /releases/affected`, `POST /hooks/git`, `GET /audit`.

## Variables de entorno

| Variable | Default | Para qué |
|---|---|---|
| `MOODLE_URL` / `MOODLE_TOKEN` | — (obligatorias para hablar con Moodle) | cuenta técnica del plugin |
| `CONTENT_REPO_URL` / `CONTENT_REPO_KEY` | — | repo remoto de contenidos (provisional, §25) |
| `CONTENT_REPO` | — | ruta local del repo que sirve `python -m courseascode.serve` |
| `COURSEASCODE_DB` | `~/.courseascode/courseascode.db` | releases y auditoría (ENG-090) |
| `COURSEASCODE_ADMIN_TOKEN` | — | rol coordinador: `release mark`, `GET /audit` |
| `COURSEASCODE_WEBHOOK_SECRET` | — | firma HMAC de `POST /hooks/git` (sin él, 503) |
| `COURSEASCODE_LOG_FORMAT` | `console` | `json` en producción; correlation id por operación |

## Docker

```bash
docker compose up --build   # raíz del repo: engine :8000 + Moodle :8080 + MariaDB
```

Imagen del servicio: `engine/Dockerfile` (usuario no-root, BD en volumen `/data`).

## Integración continua

`.github/workflows/ci.yml` corre `make check` en Python 3.12. La suite E2E de
aceptación (§32) vive en `tests/integration/` bajo el mark `integration`: se
salta sin `MOODLE_URL`/`MOODLE_TOKEN` de un moodle-docker; ver
`tests/test_moodle_contract.py` para el patrón fake/Moodle real.
