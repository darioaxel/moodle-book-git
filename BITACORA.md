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

**Fase actual:** 4 — Preview web ✅ (2026-10-07) · **Próximo:** Fase 5 — Catálogo

| Milestone | Contenido | Estado |
|---|---|---|
| M1 (F0–F4) | validate + preview | ✅ |
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

### FASE 5 — Catálogo — ⬜ pendiente

- [ ] **ENG-050**–**ENG-054**: `CatalogBuilder` (deriva del último tag; solo tags,
  nunca HEAD), `SourceRegistry` con ACL, endpoints `GET /catalog` y
  `GET /catalog/{source}/{book}/versions`, comandos `info` y `build`.

### FASE 6 — Moodle adapter — ⬜ pendiente

- [ ] **ENG-060**–**ENG-064**: interfaz `MoodleProvider`, `MoodleRestClient` (httpx),
  mapeo de las 6 funciones `local_courseascode_*` 🔌, `FakeMoodleProvider`,
  tests de contrato (fake + moodle-docker, mark `integration`).

### FASE 7 — Deployment engine — ⬜ pendiente

- [ ] **ENG-070**–**ENG-080**: `Planner` (diff → plan con CREATE/UPDATE/DELETE/UPLOAD),
  detección de eliminaciones, assets en dos pasadas, `Executor` idempotente con
  `content_hash`, cálculo de `DeploymentState`, bloqueo de RECALLED, comandos
  `deploy`/`status`, endpoints `/deploy`, `/deployment/plan`, `/deployment/status`,
  `/deployment/where` 🔌, tests E2E contra el fake.

### FASE 8 — Releases, severidad y notificaciones — ⬜ pendiente

- [ ] **ENG-090**–**ENG-095**: persistencia SQLite + SQLModel (`Release`, `AuditEvent`),
  `release mark/list`, integración de severidad en estados y planner, webhook receiver
  con verificación de firma, endpoint de afectados 🔌, auditoría.

### FASE 9 — Export, robustez y entrega — ⬜ pendiente

- [ ] **ENG-100**–**ENG-106**: `export --course`, logging structlog, errores
  recuperables, caché de checkouts/renders, suite E2E con moodle-docker 🔌,
  Dockerfile + docker-compose, documentación.

## Pista paralela 🔌 — Plugin Moodle `local_courseascode`

- [ ] Esqueleto del plugin (versión, `db/install.xml`, `db/services.php`).
- [ ] Tabla `local_courseascode_deploy`.
- [ ] Web services de escritura (`upsert_book`, `upsert_chapter`, `delete_chapter`,
  `upload_asset`, `register_deploy`, `get_deploy`).
- [ ] Páginas UI (catálogo, página de versión, panel de administración).
- [ ] Capabilities + inyección de CSS del tema.

**Hito crítico:** tabla + `upsert_book/chapter` + token listos **antes de terminar F6**.

## Registro de sesiones

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
