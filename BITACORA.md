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

**Fase actual:** 0 — Fundaciones ✅ (2026-10-01) · **Próximo:** Fase 1 — Manifests y validación

| Milestone | Contenido | Estado |
|---|---|---|
| M1 (F0–F4) | validate + preview | 🟡 F0 ✅ · F1–F4 ⬜ |
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

### FASE 1 — Manifests y validación — ⬜ pendiente

- [ ] **ENG-010** (M) Esquema pydantic de `course.yml`.
- [ ] **ENG-011** (M) Esquema pydantic de `book.yml` (sin campo `version`: lo da Git).
- [ ] **ENG-012** (M) `ManifestParser` con errores localizados (archivo, línea, campo).
- [ ] **ENG-013** (L) `Validator` con todas las reglas (§20).
- [ ] **ENG-014** (M) Salida formateada ✓/✗ con exit code 0/1.
- [ ] **ENG-015** (S) `courseascode validate [path] [--ref]` operativo.
- [ ] **ENG-016** (M) Fixture repo con 1 caso válido y ≥8 inválidos.

### FASE 2 — Git adapter — ⬜ pendiente

- [ ] **ENG-020**–**ENG-026**: interfaz `GitProvider`, `LocalGitProvider` (worktrees
  temporales), `Diff` estructurado, `VersionResolver` (tags `book/<id>/vX.Y.Z`),
  versión derivada de rama personal (`merge-base` + commits ahead → `1.2.0+juan.3`),
  detección de fuente, tests con fixture repo.

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

## Cómo actualizar esta bitácora

1. Al terminar una tarea, márcala `[x]` y anota en el registro de sesiones qué se
   hizo, qué se verificó (comandos y resultado) y qué queda pendiente.
2. Al cerrar una fase, verifica su Definition of Done contra la tasklist y consigna
   la fecha.
3. Si una decisión contradice la spec, **no la pongas en práctica**: anótala aquí
   como "decisión pendiente de validar" y consúltala.
