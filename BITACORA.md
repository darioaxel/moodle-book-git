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

**Fase actual:** 2 — Git adapter ✅ (2026-10-01) · **Próximo:** Fase 3 — Content engine (renderer)

| Milestone | Contenido | Estado |
|---|---|---|
| M1 (F0–F4) | validate + preview | 🟡 F0–F2 ✅ · F3–F4 ⬜ |
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

### FASE 3 — Content engine (renderer) — ⬜ pendiente

- [ ] **ENG-030**–**ENG-037**: pipeline markdown-it-py (CommonMark + tablas + `container`),
  Pygments inline (`noclasses=True`), sanitización con lista blanca, temas Jinja2,
  link resolver + asset resolver con adapters, `render_book(...)` y tests golden-file.

### FASE 4 — Preview web — ⬜ pendiente

- [ ] **ENG-040**–**ENG-044**: app FastAPI de preview, assets locales, adapters,
  `courseascode preview <book> [--ref] [--port 3000]` con watch, endpoint de preview
  para el plugin 🔌.

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

## Cómo actualizar esta bitácora

1. Al terminar una tarea, márcala `[x]` y anota en el registro de sesiones qué se
   hizo, qué se verificó (comandos y resultado) y qué queda pendiente.
2. Al cerrar una fase, verifica su Definition of Done contra la tasklist y consigna
   la fecha.
3. Si una decisión contradice la spec, **no la pongas en práctica**: anótala aquí
   como "decisión pendiente de validar" y consúltala.
