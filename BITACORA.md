# Bitácora de desarrollo — Moodle Course as Code

> Estado del desarrollo en todo momento. Se actualiza **al final de cada sesión de
> trabajo** (humana o de agente). Regla: si una tarea no está reflejada aquí, no está hecha.
>
> Referencias: [Especificación v0.2](docs/Especificación%20Moodle%20Course%20as%20Code%20v0.2.md) ·
> [Tasklist del engine](docs/Tasklist%20—%20Desarrollo%20courseascode-engine.md) ·
> [Diagramas de secuencia](docs/Diagramas%20de%20secuencia%20—%20Moodle%20Course%20as%20Code.md)

## Leyenda

Estados por tarea: `⬜ pendiente` · `🟡 en curso` · `✅ hecha` · `⏸️ bloqueada`

Fases y IDs según la tasklist del engine (`ENG-nnn`). El plugin Moodle
(`local_courseascode`) es pista paralela 🔌.

## Estado resumido

**Fase actual:** 9 — Export, robustez y entrega ✅ (2026-10-23) · **Beta engine completa** 🎉 · Próximo: pista 🔌 del plugin

| Milestone | Contenido | Estado |
|---|---|---|
| M1 (F0–F4) | validate + preview | ✅ |
| M2 (F5–F6) | catálogo + adapter Moodle | ✅ |
| M3 (F7) | deploy + rollback | ✅ (contra fake; moodle-docker 🔌 pendiente) |
| M4 (F8–F9) | hotfixes + entrega | ✅ (E2E real 🔌 pendiente) |
| M2 (F5–F6) | catálogo + adapter Moodle | ⬜ |
| M3 (F7) | deploy + rollback | ⬜ |
| M4 (F8–F9) | hotfixes + entrega | ⬜ |

## Progreso por fase (engine)

### FASE 0 — Fundaciones — ✅ completada el 2026-10-01

- [x] **ENG-001** (S) Repo `engine/` con `pyproject.toml` (hatchling, src-layout) y
  estructura de paquetes `courseascode/{domain,manifests,git,content,catalog,deployment,moodle,api,web,cli}`.
- [x] **ENG-002** (S) Tooling: pytest, `mypy --strict`, ruff (lint+format), pre-commit,
  `Makefile` con `test`, `lint`, `typecheck`, `check`.
- [x] **ENG-003** (S) CI: `.github/workflows/ci.yml` (Python 3.12; ruff + mypy + pytest, `working-directory: engine`).
- [x] **ENG-004** (M) Modelos de dominio: `Course`, `Book`, `Chapter`, `ContentId`,
  `SemVer` (con build metadata `1.2.0+juan.3`), `GitRef`, `DeploymentPlan`,
  `DeploymentAction`, `DeploymentResult`, `DeploymentState`, `Severity`.
  Todos serializables por pydantic (SemVer/ContentId como string).
- [x] **ENG-005** (S) Config por entorno: `MOODLE_URL`, `MOODLE_TOKEN`,
  `CONTENT_REPO_URL`, `CONTENT_REPO_KEY` (pydantic-settings; fallo ruidoso si falta alguna).
- [x] **ENG-006** (S) CLI Typer: `validate`, `preview`, `info`, `build`, `deploy`,
  `status`, `export`, `release mark/list` registrados como stubs.

**DoD Fase 0 — verificado (2026-10-01):** `pip install -e .[dev]` ✓ ·
`courseascode --help` lista los 8 comandos ✓ · CI definida ✓ ·
`SemVer` parsea y compara `1.2.0+juan.3` ✓ (tests) · `make check` verde:
ruff ✓, mypy strict sin errores ✓, 27 tests ✓.

### FASE 1 — Manifests y validación — ✅ completada el 2026-10-01

- [x] **ENG-010** (M) Esquema pydantic de `course.yml` (`CourseManifest`, `BookRef`).
- [x] **ENG-011** (M) Esquema pydantic de `book.yml` (`BookManifest`, `ChapterManifest`);
  sin campo `version` (lo da Git). Metadatos de catálogo opcionales en el esquema
  para que el validador los reporte como categoría propia.
- [x] **ENG-012** (M) `ManifestParser` con errores localizados (archivo, línea, campo),
  mensajes "YAML inválido: …" y `ManifestError` con issues agregados.
- [x] **ENG-013** (L) `Validator` con todas las reglas: YAML válido · IDs únicos
  (books y capítulos) · archivos de capítulos existentes · assets existentes
  (imágenes + cover) · enlaces internos `.md` resolubles · contenedores `:::` cerrados ·
  metadatos de catálogo presentes · `numbering` válido (enum). Escaneo Markdown con
  markdown-it-py (líneas exactas de cada referencia).
- [x] **ENG-014** (M) Salida formateada ✓/✗ por categoría con detalle
  `archivo:línea — mensaje` y exit code 0/1 (formato §20 verificado).
- [x] **ENG-015** (S) `courseascode validate [path] [--ref]` operativo sobre working
  tree y sobre refs (worktree temporal aislado en `git/worktree.py`, provisional
  hasta ENG-020/021).
- [x] **ENG-016** (M) Fixtures en `tests/fixtures/repos/`: 1 repo válido (5 capítulos,
  2 assets, enlaces internos, admonitions) y 10 inválidos (uno por regla).

**DoD Fase 1 — verificado (2026-10-01):** `validate` sobre el fixture válido →
`Validation successful.` (exit 0); sobre cada uno de los 10 fixtures inválidos,
error específico y exit 1; `--ref` valida el tag y no el working tree (test con
repo Git temporal). `make check` verde: ruff ✓, mypy strict ✓, **48 tests** ✓.

### FASE 2 — Git adapter — ✅ completada el 2026-10-01

- [x] **ENG-020** (M) Interfaz `GitProvider`: `get_ref`, `checkout_ref` (worktree
  temporal), `list_files`, `get_file`, `get_commit`, `list_tags(pattern)`,
  `diff`, `merge_base`, `commits_ahead`, `is_ancestor`, `current_branch`.
- [x] **ENG-021** (M) `LocalGitProvider` (GitPython). Worktrees por `git worktree add`
  (GitPython no los expone de forma fiable); no muta el working tree del usuario.
  `git/worktree.py` provisional de ENG-015 migrado y eliminado; el CLI `validate
  --ref` usa ahora el provider.
- [x] **ENG-022** (M) `Diff` estructurado: `FileChange` (added/modified/deleted/renamed)
  y `BookDiff` con clasificación capítulo/asset (`diff.for_book(...)`) para el
  resumen "+ Nuevo capítulo: Observer" (§22).
- [x] **ENG-023** (M) `VersionResolver`: tags `book/<id>/vX.Y.Z`, ordenación semver,
  `latest()`; tags malformados se ignoran.
- [x] **ENG-024** (M) Versión derivada de rama personal: tag base (ancestro del
  merge-base con `main`) + `commits ahead` → `1.2.0+juan.3`; sin tags base →
  `0.0.0+<source>.<ahead>`.
- [x] **ENG-025** (S) `detect_source(provider)` → rama actual (en `main`, línea oficial;
  el namespace `@dwes` es configuración de presentación).
- [x] **ENG-026** (M) Fixture Git construido en `tests/conftest.py` (`git_repo`):
  3 tags oficiales de ut03-mvc + tag de ut04-dao, rama `juan` con 3 commits
  propios, main avanza en paralelo, book sin tags (ut05).

**DoD Fase 2 — verificado (2026-10-01):** `VersionResolver` resuelve `ut03-mvc →
v1.2.0` en `main` y `1.2.0+juan.3` en la rama `juan` con 3 commits propios ✓.
`make check` verde: ruff ✓, mypy strict ✓, **69 tests** ✓. Dep añadida: GitPython.

### FASE 3 — Content engine (renderer) — ✅ completada el 2026-10-02

- [x] **ENG-030** (M) Pipeline Markdown único: preset gfm-like (CommonMark + tablas
  + tachado) + admonitions `:::note|warning|tip|important` vía plugin container
  (marcador `":"`; el plugin exige 3 repeticiones de la cadena de marcador).
- [x] **ENG-031** (M) Pygments con `noclasses=True` (estilos inline) como callback
  `highlight`; lenguaje desconocido → fallback a escape plano. Nota: el PhpLexer
  solo resalta dentro de `<?php ... ?>`.
- [x] **ENG-032** (M) Sanitización con bleach: lista blanca de tags/atributos,
  sin `on*` ni `javascript:`, y CSSSanitizer (tinycss2) que solo admite las
  propiedades que emite Pygments.
- [x] **ENG-033** (L) Sistema de temas: `theme-default` empaquetado (style.css +
  preview.html Jinja2) cargado con importlib.resources; `render_preview_page` y
  `wrap_fragment` (inyección en Moodle).
- [x] **ENG-034** (L) Link resolver: `03-model.md` → `ChapterRef` → `LinkAdapter`
  (`PreviewLinkAdapter`, `MoodleLinkAdapter` con placeholder `#chapter-<id>` para
  ENG-072); anclas `#seccion` preservadas; reescritura sobre el HTML con HTMLParser.
- [x] **ENG-035** (L) Asset resolver: recolecta `assets/...` referenciados (más
  cover), los devuelve en `RenderedBook.assets` y reescribe URLs vía `AssetAdapter`
  (`PreviewAssetAdapter`, `MoodleAssetAdapter` con placeholder `pluginfile://`).
- [x] **ENG-036** (M) API `render_book(book_dir, book, link_adapter, asset_adapter)`
  → `RenderedBook` (HTML por capítulo sanitizado + assets). `render_book_preview`
  como atajo. El `ref` se resuelve fuera (checkout aislado).
- [x] **ENG-037** (L) Tests golden-file: corpus `tests/fixtures/golden/components.md`
  con todos los componentes de §14.1 → `components.html` comparado byte a byte.

**DoD Fase 3 — verificado (2026-10-02):** el corpus renderiza todos los componentes
con estilo; el mismo `render_book` produce URLs de preview o de Moodle según el
adapter sin tocar el renderer. Deps añadidas: pygments, jinja2, bleach, tinycss2,
mdit-py-plugins, types-Pygments. `make check` verde: ruff ✓, mypy strict ✓,
**88 tests** ✓.

### FASE 4 — Preview web — ✅ completada el 2026-10-07

- [x] **ENG-040** (M) App FastAPI en `web/app.py` (`create_app(content_root, provider,
  default_ref, default_theme)`): índice de books desde `course.yml`, página de capítulo
  con TOC (vía `Theme.render_preview_page`) y selector de ref/tema inyectado como bloque
  HTML sin tocar la firma de `themes.py`.
- [x] **ENG-041** (S) Assets servidos en `/books/<id>/assets/...` con media type por
  `mimetypes`, leídos dentro del checkout (el worktree de un `?ref` se elimina al
  servir) y blindados contra path traversal.
- [x] **ENG-042** (S) `PreviewLinkAdapter`/`PreviewAssetAdapter` ya existían de Fase 3;
  cableados con `base_url=/books/<id>` (enlaces) y `/books/<id>/assets` (assets).
- [x] **ENG-043** (S) `courseascode preview <book> [--ref] [--port 3000]` operativo
  (resolución por ruta de directorio o id en `course.yml`; errores claros con exit 2).
  **Decisión "watch" documentada**: sin `watchfiles`; al servir el working tree cada
  petición re-renderiza sin caché → guardar + refrescar basta (cumple el DoD "sin
  reiniciar nada"). Con `--ref` la app fija ese ref para todas las páginas.
- [x] **ENG-044** (M) `GET /catalog/{source}/{book}/preview?ref=&chapter=&theme=`:
  sin `?ref` resuelve la última versión con `VersionResolver.latest()`; `source`
  validado con `^[a-z0-9_-]+$` (sin ACL todavía: eso es ENG-052/053).

**DoD Fase 4 — verificado (2026-10-07):** smoke test real — `preview` sobre una copia
del fixture, capítulo + asset (`200 image/png`) servidos, edición en caliente visible
sin reiniciar. Deps añadidas: fastapi, uvicorn (httpx en dev para `TestClient`).
`make check` verde: ruff ✓, mypy strict ✓, **113 tests** ✓ (25 nuevos en
`tests/test_web_preview.py`).

### FASE 5 — Catálogo — ✅ completada el 2026-10-07

- [x] **ENG-050** (M) `CatalogBuilder` (`catalog/builder.py`): modelos pydantic en
  `catalog/models.py` (`Catalog`, `CatalogEntry` con summary/tags/audience/cover/
  chapter_count/versions/latest, `CatalogVersion`). La lista de books se lee del
  `course.yml` del working tree; los metadatos y el nº de capítulos siempre del
  `book.yml` del último tag (checkout aislado por book).
- [x] **ENG-051** (S) Solo versiones taggeadas: `ut05-sin-tags` se omite aunque
  esté en `course.yml`; un capítulo añadido solo al working tree no cambia el
  `chapter_count` (test que lo demuestra).
- [x] **ENG-052** (M) `SourceRegistry` (`catalog/registry.py`): `Source` con
  propietario y visibilidad (`equipo | privada`); ACL `list_visible(caller)`;
  `default()` con la fuente oficial de Beta (`dwes/coordinacion/equipo`).
- [x] **ENG-053** (M) Endpoints en la app de `web/app.py`: `GET /catalog` (JSON
  de fuentes visibles para el llamante, header opcional `X-CourseAsCode-User`,
  auth real 🔌) y `GET /catalog/{source}/{book}/versions`. Sin repo Git → 503;
  fuente inválida/no visible → 404. `api/` queda reservado para ENG-079/093.
- [x] **ENG-054** (S) `courseascode info <book>` (formato §29: ID con namespace
  `@dwes`, Title, Type, Chapters, Assets, Git commit, Tags) y `build <book>`
  (render a `<root>/build/<id>/`: index + `<capítulo>.html` con el tema y assets
  copiados, mismo renderer — principio 5).

**DoD Fase 5 — verificado (2026-10-07):** `GET /catalog` devuelve el JSON del
fixture con versiones ordenadas asc por SemVer y metadatos completos (test
explícito). Smoke test real: `info` idéntico al formato de §29 y `build`
genera 6 HTML + 2 assets. `make check` verde: ruff ✓, mypy strict ✓,
**140 tests** ✓ (27 nuevos: `test_catalog.py`, `test_api_catalog.py`,
`test_cli_info_build.py`). Sin deps nuevas.

### FASE 6 — Moodle adapter — ⬜ pendiente

### FASE 6 — Moodle adapter — ✅ completada el 2026-10-09

- [x] **ENG-060** (M) Interfaz `MoodleProvider` (`moodle/provider.py`, patrón
  `GitProvider`): `get_course`, `get_deploy`, `upsert_book → bookid`,
  `upsert_chapter`, `delete_chapter`, `upload_asset → URL pluginfile`,
  `register_deploy`, `list_deploys`. `MoodleError` con mensaje accionable
  (`wsfunction: errorcode (exception): mensaje`). `DeployRecord` (fila de
  `local_courseascode_deploy`) y `MoodleCourse` viven en el módulo `moodle/`
  (no en `domain/`, que sigue sin importar hacia fuera).
- [x] **ENG-061** (M) `MoodleRestClient` (httpx): POST a
  `/webservice/rest/server.php` con `wstoken`/`wsfunction`/
  `moodlewsrestformat=json`; cliente inyectable (`MockTransport` en tests);
  `RetryPolicy` (3 intentos, backoff 0.2/0.5/1.0) **solo ante fallos de red**
  (`TransportError`); error Moodle → `MoodleError` sin reintento.
- [x] **ENG-062** (M) `moodle/functions.py`: `PLUGIN_FUNCTIONS`, fuente de
  verdad del contrato con payloads/respuestas documentados para el equipo del
  plugin. Asunciones anotadas ahí: `get_deploy` recibe también `source` (la
  tabla clave por `(courseid, source, content_id)`); 7ª función asumida
  `local_courseascode_list_deploys`; assets en base64; `deployed_at` ISO 8601;
  `core_course_get_courses` para `get_course`.
- [x] **ENG-063** (L) `FakeMoodleProvider` en memoria: books idempotentes por
  `(courseid, name)`, capítulos por stable id ordenados por `position`, assets
  con URL `pluginfile://<bookid>/<filename>`, tabla de deploys con historio;
  validaciones del contrato → `MoodleError`. Determinista, sin red ni reloj.
- [x] **ENG-064** (M) Tests de contrato parametrizados fake (siempre) / Moodle
  real (mark `integration`, skip sin `MOODLE_URL`/`MOODLE_TOKEN`); unitarios
  REST con `MockTransport` (protocolo, errores, retries). `httpx` movido a
  dependencies; marker `integration` registrado; `make test-integration` nuevo;
  pin de ruff en pre-commit alineado a la versión del venv (0.16.9).

**DoD Fase 6 — verificado (2026-10-09):** la suite de contrato corre contra el
fake (10 tests) y colecciona/skipea los de integración contra moodle-docker
(`pytest -m integration`: 10 skipped). `make check` verde: ruff ✓,
mypy strict ✓, **168 tests** ✓ (28 nuevos) + 10 skipped de integración.

### FASE 7 — Deployment engine — ⬜ pendiente

### FASE 7 — Deployment engine — ✅ completada el 2026-10-15

- [x] **ENG-070** (L) `Planner` (`deployment/planner.py`): diff del `RenderedBook`
  objetivo contra el HTML **actual** de Moodle → plan CREATE/UPDATE/DELETE/UPLOAD
  con resumen legible (formato §17.1). El diff contra HTML real (no solo contra
  el hash registrado) hace que un drift se sobrescriba al redeploy.
- [x] **ENG-071** (M) Eliminaciones detectadas y marcadas `requires_confirmation`;
  el executor no las aplica sin confirmación (§17.2).
- [x] **ENG-072** (L) Assets en dos pasadas: render 1 identifica assets → subida
  (solo los que cambian, por sha256) → render 2 con `MoodleAssetAdapter` de URLs
  reales. Refinado: el executor **resuelve los placeholders `#chapter-<id>` en el
  mismo deploy** (re-upsert con URL real), lo que hace el rollback byte-exacto.
- [x] **ENG-073** (L) `Executor` (`deployment/executor.py`): orden del manifest,
  idempotencia por stable ids, registro final con `content_hash` (JSON
  `{stable_id: sha256}` ordenado — permite saber qué capítulo driftó).
- [x] **ENG-074** (M) `state.py`: `compute_state → StateInfo` con NOT_DEPLOYED /
  UPDATE_AVAILABLE(+severity vía `ReleasePort`) / DRIFT_DETECTED (edición manual,
  capítulo añadido, book borrado, hash corrupto) / UP_TO_DATE / ERROR.
- [x] **ENG-075** (M) Bloqueo RECALLED en planner (`RecalledVersionError`);
  `force=True` lo salta con warning en el resultado. `ReleasePort` + 
  `NullReleasePort` por defecto; Fase 8 lo sustituye por SQLite.
- [x] **ENG-076** (M) `courseascode deploy --course --book [--version|--ref]
  [--yes] [--force]`: plan §17.1, confirmación (typer.confirm), eliminaciones con
  confirmación aparte, latest tag por defecto, exit 2 en errores.
- [x] **ENG-077** (S) Rollback = deploy con `--version` anterior; test E2E y smoke
  real verifican estado byte-exacto (mismos capítulos, mismo HTML, mismo hash).
- [x] **ENG-078** (M) `courseascode status --course`: tabla Book/Version/State/
  Severity/Commit. Sin `--course` → exit 2 documentado (el provider no lista
  cursos globalmente).
- [x] **ENG-079** (M) Endpoints `POST /deploy`, `POST /deployment/plan`,
  `GET /deployment/status`, `GET /deployment/where` (`api/deployment.py`,
  montados en `web/app.py`; sin Moodle configurado → 503 JSON; recall → 409).
- [x] **ENG-080** (L) 68 tests nuevos: planner (8), executor (10), state (12),
  service (9), **E2E contra el fake (10)**, endpoints (10), CLI (9). Ciclo
  completo: deploy → update sin duplicados → rollback exacto → drift →
  eliminación con/sin confirmación → redeploy idempotente.
- Interfaz `MoodleProvider` ampliada: `get_book(bookid)` (8ª función asumida
  `local_courseascode_get_book`) y `where_deployed(source, content_id, version)`
  (9ª asumida) — documentadas en `moodle/functions.py`. URL de asset del fake
  ahora `https://moodle.local/pluginfile.php/...` (la anterior `pluginfile://`
  era irreal y el sanitizer la eliminaba).

**DoD Fase 7 — verificado (2026-10-15):** criterios §32 de ciclo básico, update y
rollback pasan contra el fake (5–6, 7–10, 11; 13 parcial: recall/severity).
Smoke E2E real: deploy v1.0.0 → update v1.1.0 → rollback byte-exacto →
UP_TO_DATE. `make check` verde: ruff ✓, mypy strict ✓, **236 tests** ✓ (+10
skipped `integration`). Contra moodle-docker 🔌 queda para ENG-104 (Fase 9).

### FASE 8 — Releases, severidad y notificaciones — ⬜ pendiente

### FASE 8 — Releases, severidad y notificaciones — ✅ completada el 2026-10-19

- [x] **ENG-090** (M) Persistencia SQLite + SQLModel (`releases/`: `models.py`,
  `store.py`, `port.py`). `Release` (ref, source, book_id, version, severity,
  recalled, fixed_in, reason, marked_by, marked_at) y `AuditEvent` append-only.
  `ReleaseStore(db_url)`: init idempotente, sesión por operación, varias
  instancias conviven (CLI + web). BD por defecto `~/.courseascode/courseascode.db`
  (env `COURSEASCODE_DB`).
- [x] **ENG-091** (M) `courseascode release mark <ref> --severity --recall
  --fixed-in --reason` real: upsert en SQLite, solo coordinador
  (`COURSEASCODE_ADMIN_TOKEN`; sin token o incorrecto → exit 2), `--reason`
  obligatorio si critical o recall (flujo §11.1). `release list <book>` con
  tabla por release.
- [x] **ENG-092** (S) `SqlReleasePort` implementa `ReleasePort` y se enchufa en
  `DeploymentService(releases=...)`; la app web lo construye desde settings
  (sin BD → `NullReleasePort`). Circuito cerrado: severidad en `StateInfo` y
  bloqueo RECALLED del planner funcionan con datos reales.
- [x] **ENG-093** (M) Webhook `POST /hooks/git` (`api/hooks.py`): firma
  HMAC-SHA256 del body crudo, header `X-CourseAsCode-Signature: sha256=<hex>`
  (estilo GitHub), secreto en `COURSEASCODE_WEBHOOK_SECRET`; sin secreto →
  deshabilitado, firma inválida → 401. Eventos válidos quedan en auditoría.
  Recálculo de cachés = no-op documentado (llega en ENG-103).
- [x] **ENG-094** (M) `GET /releases/affected?source=&book=&version=` (`api/releases.py`):
  cursos con esa versión desplegada (vía `where_deployed`) con severity/recall/
  fixed_in/reason y `deployed_by` (proxy de "profesor" sin consultar usuarios
  Moodle; la notificación la envía el plugin 🔌 — el servicio solo calcula).
- [x] **ENG-095** (S) Auditoría: `store.mark()` registra `release.mark` como
  **invariante del store** (todo writer queda auditado sin duplicar), los
  deploys registran `deploy` desde el pipeline, webhooks válidos `webhook.git`.
  Lectura admin: `GET /audit?book_id=` exige token de administrador.
- Dep nueva: `sqlmodel`. Corrección de cierre: se eliminó el `record_event`
  duplicado en CLI y en el helper de tests — la auditoría del mark vive en el
  store (un solo evento por marca).

**DoD Fase 8 — verificado (2026-10-19):** smoke E2E real del flujo §11.1 —
deploy en 2 cursos → `release mark` critical+recall → `status` muestra badge
crítico ✓ → redeploy de la RECALLED falla (`RecalledVersionError`) y `--force`
pasa con warning ✓ → `where` lista `[101, 102]` ✓ → auditoría con
`deploy` + `release.mark` ✓. `make check` verde: ruff ✓, mypy strict ✓,
**274 tests** ✓ (38 nuevos: store, hooks, API releases, CLI release, E2E del
DoD). 10 skipped `integration` (sin moodle-docker 🔌).

### FASE 9 — Export, robustez y entrega — ⬜ pendiente

### FASE 9 — Export, robustez y entrega — ✅ completada el 2026-10-23

- [x] **ENG-100** (M) `courseascode export --course C`: genera
  `deployments/<curso>.yml` (vista exportable, §9) desde el estado del plugin;
  bytes estables (re-export idempotente).
- [x] **ENG-101** (M) Logging structlog con **correlation id** por operación
  (contextvar + `X-Correlation-Id` en la API); eventos `deploy.start/plan/
  execute/error`; formato `console`/`json` (`COURSEASCODE_LOG_FORMAT`).
- [x] **ENG-102** (M) Errores recuperables: fallo a mitad registra deploy con
  `status="error"` (estado ERROR) y propaga `DeploymentExecutionError`
  accionable ("relanza el mismo deploy"); la reejecución recupera sin
  duplicar. `FakeMoodleProvider.fail_next(op)` para inyección de fallos.
- [x] **ENG-103** (M) `RenderCache` en memoria (thread-safe, TTL 15 min, 64
  entradas, reloj inyectable): solo refs inmutables (tag/commit, clave por
  sha); working tree y ramas nunca. Invalidación completa vía webhook.
- [x] **ENG-104** (L) `tests/integration/test_acceptance.py`: los criterios
  §32 automatizables (importación, actualización, rollback, hotfix) contra
  moodle-docker; mark `integration` + skipif sin credenciales. El 12
  (gobernanza Git) es de plataforma, no del engine (docstring).
- [x] **ENG-105** (S) `engine/Dockerfile` (slim, no-root, healthcheck, BD en
  volumen) + `engine/.dockerignore` + `docker-compose.yml` en raíz (engine +
  Moodle + MariaDB, mount preparado para el plugin 🔌) + módulo de arranque
  `python -m courseascode.serve` (env `CONTENT_REPO`, `HOST`/`PORT`).
- [x] **ENG-106** (M) Documentación: `engine/README.md` reescrito (guía de
  desarrollo completa), `docs/Guía de autor.md` (manifests, Markdown, flujo de
  publicación), `docs/Guía de operación.md` (tokens, despliegue, releases,
  troubleshooting, límites de la Beta).
- Incidentes de cierre: bug `cache or RenderCache()` en `create_app` (un caché
  vacío es falsy por `__len__` y se descartaba); duplicación de auditoría del
  mark centralizada en el store; correcciones PLR2004/UP046/SIM105/E501 y
  expectativas de tests (GitProviderError/MoodleError según fase del pipeline).

**DoD Fase 9 — verificado (2026-10-23):** `make check` verde: ruff ✓,
mypy strict ✓, **293 tests** ✓ (43 nuevos en la fase: export, logging,
error recovery, render cache, integración §32). `pytest -m integration`:
14 tests coleccionados, skipeados sin moodle-docker. Deps nuevas: structlog,
sqlmodel (Fase 8). Docker no verificable en este entorno (sin docker): el
entrypoint sí lo es (`build_app()` con y sin `CONTENT_REPO`).

**BETA DEL ENGINE COMPLETA** (Fases 0–9, ENG-001–106). Pendiente fuera del
engine: pista paralela 🔌 del plugin `local_courseascode` y, con él, la
verificación E2E real (ENG-104 contra moodle-docker).

## Pista paralela 🔌 — Plugin Moodle `local_courseascode`

- [ ] Esqueleto del plugin (versión, `db/install.xml`, `db/services.php`).
- [ ] Tabla `local_courseascode_deploy`.
- [ ] Web services de escritura (`upsert_book`, `upsert_chapter`, `delete_chapter`,
  `upload_asset`, `register_deploy`, `get_deploy`).
- [ ] Páginas UI (catálogo, página de versión, panel de administración).
- [ ] Capabilities + inyección de CSS del tema.

**Hito crítico:** tabla + `upsert_book/chapter` + token listos **antes de terminar F6**.

## Registro de sesiones

### 2026-10-23 — Sesión 10: Fase 9 completa — Beta del engine terminada

- **ENG-100 a ENG-106 implementados**: `export --course` (YAML estable),
  logging structlog con correlation id, errores de despliegue recuperables
  (registro `status="error"` + mensaje accionable + reejecución idempotente),
  `RenderCache` por sha inmutable, suite de aceptación §32 bajo mark
  `integration`, Dockerfile + docker-compose + `python -m courseascode.serve`,
  y documentación completa (README del engine, Guía de autor, Guía de
  operación).
- Cierres hechos a mano tras la interrupción del agente: tests de logging/
  error-recovery/render-cache (14), bug del caché descartado por falsedad en
  `create_app`, tipado de `serve.py`, lint y docs.
- **DoD verificado**: `make check` verde (ruff ✓, mypy strict ✓, **293 tests**
  ✓); integración colecciona y skipea sin moodle-docker. **M4 cerrado — Beta
  del engine completa (ENG-001–106).**
- **Pendiente fuera del engine:** pista 🔌 del plugin `local_courseascode`
  (tabla, web services, páginas) y la verificación E2E real contra
  moodle-docker cuando el plugin exista.

### 2026-10-19 — Sesión 9: Fase 8 completa (releases, severidad y notificaciones)

- **ENG-090 a ENG-095 implementados**: `ReleaseStore` SQLite + SQLModel
  (`Release`, `AuditEvent` append-only), `SqlReleasePort` cerrando el circuito
  con planner/estados, CLI `release mark/list` con token de coordinador,
  webhook `POST /hooks/git` con firma HMAC-SHA256, `GET /releases/affected` y
  auditoría (`release.mark` como invariante del store; lectura admin en
  `GET /audit`). 38 tests nuevos.
- Incidentes de cierre: la auditoría del mark se centralizó en el store
  (el CLI y los helpers de test duplicaban el evento → 2 tests en rojo hasta
  eliminar los `record_event` redundantes).
- **DoD verificado**: smoke E2E del hotfix crítico de §11.1 (badge crítico,
  recall bloquea, `--force` avisa, `where` afectados, auditoría completa).
  `make check` verde: ruff ✓, mypy strict ✓, **274 tests** ✓.
- **Pendiente para la próxima sesión:** Fase 9 (ENG-100–106, última): `export
  --course`, logging structlog, errores recuperables, caché de checkouts/
  renders, suite E2E con moodle-docker 🔌 (mark `integration`), Dockerfile +
  docker-compose y documentación (guía de autor, guía de operación). Deps
  previstas: structlog.

### 2026-10-15 — Sesión 8: Fase 7 completa (deployment engine)

- **ENG-070 a ENG-080 implementados**: `Planner` (diff contra HTML real de
  Moodle), `Executor` idempotente con resolución de placeholders en caliente,
  servicio de pipeline §17 (dos pasadas de assets), estados (§19) con drift,
  bloqueo RECALLED con `--force`, CLI `deploy`/`status`, 4 endpoints de
  deployment y 68 tests nuevos con E2E completo contra el fake.
- Decisiones: `content_hash` = JSON `{stable_id: sha256}`; `ReleasePort` con
  `NullReleasePort` (Fase 8 lo vuelca a SQLite); 8ª/9ª funciones asumidas del
  plugin (`get_book`, `where_deployed`) documentadas en `functions.py`; URL de
  asset del fake corregida a `pluginfile.php` real.
- **DoD verificado**: §32 (ciclos básico/update/rollback) contra el fake; smoke
  E2E real con rollback byte-exacto. `make check` verde: ruff ✓, mypy strict ✓,
  **236 tests** ✓. **M3 (deploy + rollback) cerrado contra el fake.**
- **Pendiente para la próxima sesión:** Fase 8 (ENG-090–095): persistencia
  SQLite + SQLModel (`Release`, `AuditEvent`), `release mark/list` real
  (sustituye `NullReleasePort`), webhook `POST /hooks/git` con firma, endpoint
  de afectados 🔌 y auditoría. Deps nuevas previstas: sqlmodel.

### 2026-10-09 — Sesión 7: Fase 6 completa (Moodle adapter)

- **ENG-060 a ENG-064 implementados**: `MoodleProvider` (ABC), `MoodleRestClient`
  (httpx, retries con backoff solo en red), `PLUGIN_FUNCTIONS` como fuente de
  verdad del contrato con el plugin 🔌, `FakeMoodleProvider` determinista y
  tests de contrato parametrizados fake/Moodle real (mark `integration`).
- Decisiones: `DeployRecord` y `MoodleCourse` en `moodle/` (no en `domain/`);
  cliente httpx inyectable; `RetryPolicy` desactivable en tests; asunciones del
  contrato documentadas en `functions.py` (`get_deploy` con `source`, 7ª
  función `list_deploys`, assets base64, `deployed_at` ISO 8601).
- Tooling: `httpx` a dependencies; marker `integration` registrado con target
  `make test-integration`; pin de ruff en pre-commit alineado al venv.
- **DoD verificado**: contrato corre contra fake; integración colecciona y
  skipea sin Moodle. `make check` verde: ruff ✓, mypy strict ✓, **168 tests** ✓
  (+10 skipped). **M2 (catálogo + adapter) cerrado.**
- **Pendiente para la próxima sesión:** Fase 7 (ENG-070–080): `Planner`
  (diff → plan CREATE/UPDATE/DELETE/UPLOAD), assets en dos pasadas, `Executor`
  idempotente con `content_hash`, estados, comandos `deploy`/`status`,
  endpoints `/deploy`… y tests E2E contra el fake. Es la fase más larga del
  proyecto junto a F3 — vigilar especialmente ENG-072 (dos pasadas).

### 2026-10-07 — Sesión 6: Fase 5 completa (catálogo)

- **ENG-050 a ENG-054 implementados**: `CatalogBuilder` + modelos pydantic,
  `SourceRegistry` con ACL, endpoints `GET /catalog` y
  `/catalog/{source}/{book}/versions` en la app FastAPI (header opcional
  `X-CourseAsCode-User`; auth real pendiente del plugin 🔌) y comandos CLI
  `info` (formato §29) y `build` (render a disco con tema, principio 5).
- Decisiones: lista de books del `course.yml` del working tree; metadatos y
  capítulos siempre del último tag; versiones ordenadas asc con `latest`
  explícito; namespace `@dwes` = fuente oficial del registry (presentación).
- **DoD verificado**: `GET /catalog` con JSON completo y versiones ordenadas;
  smoke test real de `info`/`build`. `make check` verde: ruff ✓, mypy strict ✓,
  **140 tests** ✓. Sin deps nuevas.
- **Pendiente para la próxima sesión:** Fase 6 (ENG-060–064): interfaz
  `MoodleProvider`, `MoodleRestClient` (httpx), `FakeMoodleProvider` y tests de
  contrato. Prerequisito: añadir `httpx` a dependencies (ya está en dev) y
  acordar con el equipo del plugin los 6 contratos `local_courseascode_*` 🔌.
  **Hito crítico plugin:** tabla + `upsert_book/chapter` + token antes de
  terminar F6.

### 2026-10-07 — Sesión 5: Fase 4 completa (preview web)

- **ENG-040 a ENG-044 implementados**: app FastAPI (`web/app.py`) con índice de
  books, página de capítulo con TOC + selector de ref/tema, assets servidos
  blindados contra traversal, comando `preview [--ref] [--port]` y endpoint
  público `GET /catalog/{source}/{book}/preview?ref=` (latest tag por defecto
  vía `VersionResolver`).
- **Decisión clave — watch**: re-render por petición sin caché en vez de
  `watchfiles`; guardar + refrescar cumple el DoD sin dependencias extra.
  Documentada en la docstring de `web/app.py` y en la entrada de fase.
- Incidentes resueltos al verificar: `FileResponse` leía el asset en lazy tras
  eliminar el worktree del ref (se lee dentro del checkout); un test CLI
  arrancaba uvicorn real y colgaba la suite (mock añadido).
- Deps nuevas: fastapi, uvicorn (+ httpx en dev). **M1 (validate + preview) cerrado.**
- **DoD verificado**: smoke test real con `courseascode preview` (capítulo, asset
  200, edición en caliente sin reiniciar). `make check` verde: ruff ✓,
  mypy strict ✓, **113 tests** ✓.
- **Pendiente para la próxima sesión:** Fase 5 (ENG-050–054): `CatalogBuilder`
  (del último tag, nunca HEAD), `SourceRegistry` con ACL, endpoints
  `GET /catalog` y `/catalog/{source}/{book}/versions`, comandos `info` y `build`.

### 2026-10-01 — Sesión 1: arranque del proyecto

- Estudiada la documentación en `docs/` (spec v0.2, diagramas S1–S10, tasklist, prompt 0.1 histórico).
- Decisión de estructura: monorepo; el engine vive en `engine/` con src-layout
  (hatchling). Podrá extraerse a repo propio sin cambios.
- **Fase 0 completa** (ENG-001 a ENG-006) con DoD verificado en local:
  27 tests, ruff y mypy `--strict` en verde, `courseascode --help` operativo.
- Añadidos `py.typed` (mypy strict) y hooks pydantic en `SemVer`/`ContentId`.
- Creada esta bitácora y README del proyecto con diagramas.
- **Pendiente para la próxima sesión:** Fase 1 (ENG-010 a ENG-016). Prerequisitos:
  añadir dependencias PyYAML + GitPython al `pyproject.toml` al empezar ENG-010/020.

### 2026-10-01 — Sesión 2: Fase 1 completa (manifests y validación)

- **ENG-010 a ENG-016 implementados**: esquemas pydantic (`CourseManifest`,
  `BookManifest`), `ManifestParser` con errores localizados, `Validator` con las
  reglas de §20, salida ✓/✗ con exit 0/1, comando `validate [--ref]` (worktree
  temporal provisional en `git/worktree.py`) y fixtures (1 válido + 10 inválidos).
- Dependencias añadidas: `pyyaml`, `markdown-it-py`, `types-PyYAML`.
- **DoD verificado**: fixture válido → `Validation successful.`; los 10 inválidos
  fallan con su error específico; `--ref` valida el tag, no el disco.
  `make check` verde: ruff ✓, mypy strict ✓, **48 tests** ✓.
- **Pendiente para la próxima sesión:** Fase 2 (ENG-020–026). Prerequisitos:
  añadir `GitPython` al `pyproject.toml`; al formalizar `GitProvider`, migrar
  `git/worktree.py` (ENG-015) a la interfaz nueva.

### 2026-10-01 — Sesión 3: Fase 2 completa (Git adapter)

- **ENG-020 a ENG-026 implementados**: interfaz `GitProvider` (10 operaciones),
  `LocalGitProvider` (GitPython + worktrees por CLI), `Diff`/`BookDiff`
  clasificado, `VersionResolver` (tags y versión derivada `1.2.0+juan.3`),
  `detect_source`, fixture Git en `tests/conftest.py` y 21 tests nuevos.
- Migrado el worktree provisional de ENG-015 al provider (el CLI `validate --ref`
  ya no usa `git/worktree.py`, eliminado).
- Dep añadida: `GitPython>=3.1.43`.
- **DoD verificado**: rama `juan` → `1.2.0+juan.3` (3 commits propios); `main` →
  `1.2.0+main.0`. `make check` verde: ruff ✓, mypy strict ✓, **69 tests** ✓.
- **Pendiente para la próxima sesión:** Fase 3 (ENG-030–037, renderer). Prerequisitos:
  añadir `Pygments`, `Jinja2` y `bleach` (o allowlist propia) al `pyproject.toml`.
  Tareas de mayor riesgo según tasklist: ENG-034 (link resolver) y ENG-035 (asset resolver).

### 2026-10-02 — Sesión 4: Fase 3 completa (content engine / renderer)

- **ENG-030 a ENG-037 implementados**: pipeline Markdown único (gfm-like +
  admonitions `:::` + Pygments inline), sanitización bleach con CSSSanitizer,
  tema `theme-default` (CSS + plantilla Jinja2), link/asset resolvers con
  adapters preview/Moodle, API `render_book` y tests golden-file
  (`tests/fixtures/golden/components.{md,html}`).
- Decisiones y hallazgos: el plugin container de mdit-py-plugins exige el
  marcador `":"` (3 repeticiones = `:::`); el PhpLexer solo resalta dentro de
  `<?php`; linkify desactivado (evita dep linkify-it-py); overrides mypy para
  bleach/mdit_py_plugins; deps nuevas: pygments, jinja2, bleach, tinycss2,
  mdit-py-plugins, types-Pygments.
- **DoD verificado**: corpus completo renderizado; mismos adapters cambian URLs
  sin tocar el renderer. `make check` verde: ruff ✓, mypy strict ✓, **88 tests** ✓.
- **Pendiente para la próxima sesión:** Fase 4 (ENG-040–044): app FastAPI de
  preview, comando `preview` con watch y endpoint público para el plugin.
  Prerequisito: añadir `fastapi` + `uvicorn` al pyproject.

## Cómo actualizar esta bitácora

1. Al terminar una tarea, márcala `[x]` y anota en el registro de sesiones qué se
   hizo, qué se verificó (comandos y resultado) y qué queda pendiente.
2. Al cerrar una fase, verifica su Definition of Done contra la tasklist y consigna
   la fecha.
3. Si una decisión contradice la spec, **no la pongas en práctica**: anótala aquí
   como "decisión pendiente de validar" y consúltala.
