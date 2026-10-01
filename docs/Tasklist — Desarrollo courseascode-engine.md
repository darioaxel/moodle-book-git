# Tasklist — Desarrollo de `courseascode-engine` (servicio Python)

> Basado en la Especificación Beta 0.2. Solo cubre el **engine Python**; el plugin
> Moodle `local_courseascode` es una pista paralela (sus puntos de contacto están
> marcados con 🔌). IDs de tarea `ENG-nnn` para trazabilidad.
>
> Leyenda de estimación: **S** < 1 día · **M** 1–3 días · **L** 3–5 días · **XL** > 5 días.

---

## Convenciones transversales

- Todo módulo incluye tests unitarios desde el primer commit (pytest).
- Tipado estricto: `mypy --strict` sin errores; `ruff` para lint/formato.
- Los modelos de `domain/` no importan nada de `git/`, `moodle/`, `content/` ni `api/` (dependencias solo hacia dentro).
- Cada fase termina con su "Definition of Done" (DoD) verificable.
- Fixture repos Git de prueba en `tests/fixtures/` (repo con tags, ramas y contenido de ejemplo).

---

## FASE 0 — Fundaciones del proyecto

**Objetivo:** esqueleto instalable, tooling y modelos de dominio puros.

- [ ] **ENG-001** (S) Inicializar repo `courseascode-engine`: `pyproject.toml` (hatchling o poetry), estructura de paquetes `courseascode/{domain,manifests,git,content,catalog,deployment,moodle,api,web,cli}`.
- [ ] **ENG-002** (S) Tooling: pytest, mypy strict, ruff, pre-commit, `Makefile`/`justfile` con `test`, `lint`, `typecheck`.
- [ ] **ENG-003** (S) CI básica (GitHub Actions/GitLab CI): lint + typecheck + tests en Python 3.12.
- [ ] **ENG-004** (M) Modelos de dominio (pydantic): `Course`, `Book`, `Chapter`, `ContentId` (source+id), `SemVer` (con soporte de build metadata `1.2.0+juan.3`), `GitRef`, `DeploymentPlan`, `DeploymentAction` (CREATE/UPDATE/DELETE/UPLOAD), `DeploymentResult`, `DeploymentState` (NOT_DEPLOYED, UP_TO_DATE, UPDATE_AVAILABLE+severity, DRIFT_DETECTED, DEPLOYING, ERROR).
- [ ] **ENG-005** (S) Gestión de configuración por entorno: `MOODLE_URL`, `MOODLE_TOKEN`, `CONTENT_REPO_URL`, `CONTENT_REPO_KEY` (pydantic-settings; fallo ruidoso si falta alguna).
- [ ] **ENG-006** (S) Esqueleto CLI con Typer: comandos registrados como stubs que devuelven "not implemented".

**DoD Fase 0:** `pip install -e .` funciona; `courseascode --help` lista todos los comandos; CI en verde; `SemVer` parsea y compara correctamente incluido `1.2.0+juan.3`.

---

## FASE 1 — Manifests y validación

**Objetivo:** `courseascode validate` completo (§20 y §6 de la spec).

- [ ] **ENG-010** (M) Esquema pydantic de `course.yml` (id, title, books[] con id+path).
- [ ] **ENG-011** (M) Esquema pydantic de `book.yml` (id, type, title, description, summary, tags, audience, cover opcional, numbering enum, chapters[] con id+title+file). Sin campo `version` (lo da Git).
- [ ] **ENG-012** (M) `ManifestParser`: carga y parseo con errores localizados (archivo, línea, campo).
- [ ] **ENG-013** (L) `Validator` con todas las reglas: YAML válido · IDs únicos (books y chapters) · archivos de capítulos existentes · assets referenciados existentes · enlaces internos resolubles (`.md` destino existe en el manifest) · Markdown parseable · metadatos de catálogo presentes · `numbering` válido.
- [ ] **ENG-014** (M) Salida formateada del validador (✓/✗ por categoría, detalle de errores con archivo y línea; exit code 0/1).
- [ ] **ENG-015** (S) Comando `courseascode validate [path]` operativo sobre working tree y sobre un ref (`--ref`).
- [ ] **ENG-016** (M) Fixture repo con casos válidos y al menos 8 casos inválidos (uno por regla).

**DoD Fase 1:** `courseascode validate` sobre el fixture válido devuelve `Validation successful.`; sobre cada fixture inválido, error específico y exit 1. Preparado para correr como status check en PRs.

---

## FASE 2 — Git adapter

**Objetivo:** abstracción Git completa y resolución de versiones (§7, §8 de la spec).

- [ ] **ENG-020** (M) Interfaz `GitProvider`: `get_ref(ref)`, `checkout_ref(ref) → Worktree`, `list_files(ref, path)`, `get_file(ref, path)`, `get_commit(ref)`, `list_tags(pattern)`, `diff(ref_a, ref_b) → Diff`, `merge_base(ref_a, ref_b)`, `commits_ahead(base, ref)`.
- [ ] **ENG-021** (M) `LocalGitProvider` con GitPython. Checkout aislado por worktree temporal (no muta el working tree del usuario).
- [ ] **ENG-022** (M) `Diff` estructurado: archivos añadidos/modificados/eliminados, clasificados por capítulo/asset (para el resumen `+ Nuevo capítulo: Observer`).
- [ ] **ENG-023** (M) `VersionResolver`: patrón de tags `book/<id>/vX.Y.Z`; última versión de un Book; ordenación semver correcta.
- [ ] **ENG-024** (M) Cálculo de versión derivada de rama personal: tag oficial base (merge-base con `main`) + commits ahead → `1.2.0+juan.3`.
- [ ] **ENG-025** (S) Detección de fuente: rama actual del repo compartido → `source` = nombre de rama.
- [ ] **ENG-026** (M) Tests sobre fixture repo con tags, ramas personales y merges (incluye casos: sin tag base, múltiples tags, rama 0 commits ahead).

**DoD Fase 2:** dado el fixture, `VersionResolver` resuelve `@dwes/ut03-mvc → v1.2.0` en `main` y `1.2.0+juan.3` en la rama `juan` con 3 commits propios.

---

## FASE 3 — Content engine (renderer)

**Objetivo:** el renderer único del sistema (§13–§16 de la spec). Es el corazón: preview y deploy lo comparten.

- [ ] **ENG-030** (M) Pipeline Markdown con markdown-it-py: CommonMark + tablas + `container` para admonitions (`note`, `warning`, `tip`, `important`).
- [ ] **ENG-031** (M) Resaltado Pygments con `noclasses=True` (estilos inline) para bloques de código con lenguaje.
- [ ] **ENG-032** (M) Sanitización HTML con lista blanca explícita (bleach o allowlist propia): sin `<script>`, sin atributos `on*`, sin `javascript:` en enlaces.
- [ ] **ENG-033** (L) Sistema de temas: Jinja2 + CSS por tema; `theme-default` completo (tipografía, tablas, blockquotes, código, admonitions, imágenes responsivas). El Markdown nunca contiene clases del tema.
- [ ] **ENG-034** (L) **Link resolver**: `03-model.md` → destino abstracto `ChapterRef(id=model)`. El renderer emite URLs a través de un `LinkAdapter`: `PreviewLinkAdapter` (URLs locales) y `MoodleLinkAdapter` (URLs de capítulo Moodle). Anclas internas `#seccion` preservadas.
- [ ] **ENG-035** (L) **Asset resolver**: recolecta `assets/...` referenciados, los devuelve como lista de assets a subir, y reescribe URLs vía `AssetAdapter` (preview: servir local; Moodle: URL `pluginfile.php` — ver ENG-054 para la estrategia de dos pasadas).
- [ ] **ENG-036** (M) API pública del módulo: `render_book(book, ref, link_adapter, asset_adapter, theme) → RenderedBook` (HTML por capítulo + lista de assets).
- [ ] **ENG-037** (L) Tests golden-file: corpus de Markdown con todos los componentes de §14.1 → HTML esperado por tema. Cualquier cambio de output rompe el test a propósito.

**DoD Fase 3:** el corpus de prueba renderiza todos los componentes con estilo; el mismo `render_book` produce URLs de preview o de Moodle según el adapter, sin tocar el renderer.

---

## FASE 4 — Preview web

**Objetivo:** `courseascode preview` y la preview embebible (§13).

- [ ] **ENG-040** (M) App FastAPI `web/`: lista de books del repo, vista de Book con índice de capítulos + contenido renderizado, selector de ref (tag/rama) y de tema.
- [ ] **ENG-041** (S) Servido de assets locales en preview (ruta `/assets/...`).
- [ ] **ENG-042** (S) `PreviewLinkAdapter` + `PreviewAssetAdapter` (implementaciones de ENG-034/035).
- [ ] **ENG-043** (S) Comando `courseascode preview <book> [--ref] [--port 3000]` con recarga al cambiar archivos (watch).
- [ ] **ENG-044** (M) Endpoint público de preview renderizada (`GET /catalog/{source}/{book}/preview?ref=`) que consumirá el plugin 🔌.

**DoD Fase 4:** un autor escribe en VS Code, guarda, y ve el cambio con tema en `localhost:3000` sin reiniciar nada.

---

## FASE 5 — Catálogo

**Objetivo:** derivar el catálogo del repo y exponerlo por API (§12).

- [ ] **ENG-050** (M) `CatalogBuilder`: recorre `books/` en el último tag de cada Book; deriva entrada de catálogo desde `book.yml` (título, summary, tags, audience, cover, nº capítulos, versiones disponibles).
- [ ] **ENG-051** (S) Solo versiones taggeadas aparecen; nunca HEAD.
- [ ] **ENG-052** (M) Modelo `SourceRegistry`: fuentes con propietario y visibilidad (`equipo | privada`). En Beta: una fuente oficial; la estructura y la ACL quedan implementadas y testeadas aunque solo haya una fuente.
- [ ] **ENG-053** (M) Endpoints: `GET /catalog`, `GET /catalog/{source}/{book}/versions` (filtrado por identidad del llamante 🔌).
- [ ] **ENG-054** (S) Comandos `courseascode info <book>` y `courseascode build <book>` (render a disco sin desplegar).

**DoD Fase 5:** `GET /catalog` devuelve el JSON del fixture con versiones ordenadas y metadatos completos.

---

## FASE 6 — Moodle adapter

**Objetivo:** cliente del plugin Moodle, con fake para tests (§5.3–5.4).

- [ ] **ENG-060** (M) Interfaz `MoodleProvider`: `get_course`, `get_deploy(courseid, source, content_id)`, `upsert_book`, `upsert_chapter`, `delete_chapter`, `upload_asset`, `register_deploy`, `list_deploys(courseid)`.
- [ ] **ENG-061** (M) `MoodleRestClient` (httpx): protocolo REST de Moodle web services (`wstoken`, `wsfunction`, `moodlewsrestformat=json`), manejo de errores Moodle (`errorcode`, `exception`), retries con backoff en fallos de red.
- [ ] **ENG-062** (M) Mapeo de las 6 funciones del plugin 🔌 (`local_courseascode_*`). Contratos documentados con el equipo del plugin: payloads y respuestas.
- [ ] **ENG-063** (L) `FakeMoodleProvider` en memoria: simula Books, capítulos (por stable id), assets y tabla de despliegues. Permite testear el deployment engine sin Moodle.
- [ ] **ENG-064** (M) Tests de contrato: mismas pruebas corren contra `FakeMoodleProvider` y (mark `integration`) contra moodle-docker real 🔌.

**DoD Fase 6:** el fake reproduce fielmente el contrato; un test que usa el provider pasa indistintamente contra fake y Moodle real.

---

## FASE 7 — Deployment engine

**Objetivo:** planner + executor idempotentes; el ciclo deploy/rollback (§17–§19).

- [ ] **ENG-070** (L) `Planner`: compara `RenderedBook` objetivo con estado actual (vía `get_deploy` + capítulos en Moodle) → `DeploymentPlan` con acciones CREATE/UPDATE/DELETE/UPLOAD, incluido resumen legible (formato §17.1).
- [ ] **ENG-071** (M) Detección de eliminaciones: capítulos presentes en Moodle y ausentes en target → acción DELETE marcada `requires_confirmation`.
- [ ] **ENG-072** (L) Estrategia de assets en dos pasadas: (1) subir assets → obtener URLs `pluginfile.php`; (2) render final con `MoodleAssetAdapter` alimentado con esas URLs. (Alternativa aceptable: render con placeholders + patch post-upload; documentar la elegida.)
- [ ] **ENG-073** (L) `Executor`: aplica el plan vía `MoodleProvider`; orden de capítulos por posición del manifest; idempotencia garantizada por stable ids; registro final con `content_hash` (hash del HTML desplegado por capítulo).
- [ ] **ENG-074** (M) Cálculo de `DeploymentState`: UP_TO_DATE / UPDATE_AVAILABLE (+severity desde release registry) / DRIFT_DETECTED (comparando content_hash con el HTML actual del Book 🔌) / ERROR.
- [ ] **ENG-075** (M) Bloqueo de versiones RECALLED en planner (`--force` lo salta, con warning en auditoría).
- [ ] **ENG-076** (M) Comando `courseascode deploy`: muestra plan, pide confirmación (o `--yes`), ejecuta, imprime resultado.
- [ ] **ENG-077** (S) Rollback = deploy con `--version` anterior. Sin código especial: verificar con test que v1.1.0 → v1.0.0 restaura el estado exacto.
- [ ] **ENG-078** (M) Comando `courseascode status [--course]`: tabla de estados por Book.
- [ ] **ENG-079** (M) Endpoints: `POST /deploy`, `POST /deployment/plan`, `GET /deployment/status`, `GET /deployment/where` (consulta inversa: cursos con version X) 🔌.
- [ ] **ENG-080** (L) Tests E2E contra `FakeMoodleProvider`: ciclo completo deploy → update (sin duplicados) → eliminación con confirmación → rollback → drift.

**DoD Fase 7:** los criterios de aceptación §32 (ciclos básico, actualización y rollback) pasan de forma automatizada contra el fake y contra moodle-docker 🔌.

---

## FASE 8 — Releases, severidad y notificaciones

**Objetivo:** ciclo de vida de versiones y hotfixes (§11).

- [ ] **ENG-090** (M) Persistencia del servicio (SQLite + SQLModel): `Release` (ref, version, source, severity, recalled, fixed_in, reason, marked_by, marked_at) y `AuditEvent`.
- [ ] **ENG-091** (M) `courseascode release mark/list`: marcar severidad, recall, motivo. Solo rol coordinador (token propio del servicio).
- [ ] **ENG-092** (S) Integración del estado de release en `DeploymentState` (severity → badge crítico) y en planner (ENG-075).
- [ ] **ENG-093** (M) Webhook receiver `POST /hooks/git`: eventos de push/merge/tag de la plataforma → invalidar cachés y recalcular estados. Verificación de firma del webhook.
- [ ] **ENG-094** (M) Endpoint de afectados por versión crítica: dado `(source, book, version)` → lista de cursos + profesores 🔌 (el plugin envía la notificación Moodle; el servicio solo calcula).
- [ ] **ENG-095** (S) Auditoría: todo deploy, mark y recall queda en `AuditEvent` con quién/cuándo/qué.

**DoD Fase 8:** marcar v1.3.0 como critical hace que `status` la muestre con badge crítico, que `deploy --version 1.3.0` falle, y que `/deployment/where` liste los cursos afectados.

---

## FASE 9 — Export, robustez y entrega

**Objetivo:** cerrar la Beta.

- [ ] **ENG-100** (M) `courseascode export --course C`: genera `deployments/<curso>.yml` desde el estado del plugin (vista exportable, §9) 🔌.
- [ ] **ENG-101** (M) Logging estructurado (structlog) con correlation id por deploy; trazabilidad CLI ↔ API ↔ Moodle.
- [ ] **ENG-102** (M) Manejo de errores de despliegue: estado ERROR recuperable relanzando el mismo deploy (idempotencia); mensajes accionables.
- [ ] **ENG-103** (M) Caché de checkouts/renders por commit (los tags son inmutables → caché agresiva segura).
- [ ] **ENG-104** (L) Suite E2E completa en CI con moodle-docker 🔌: los 13 criterios de aceptación de §32.
- [ ] **ENG-105** (S) Dockerfile del servicio + docker-compose de desarrollo (engine + Moodle + plugin).
- [ ] **ENG-106** (M) Documentación: README de desarrollo, guía de autor (formato de manifests), guía de operación (tokens, despliegue del servicio).

**DoD Fase 9:** CI verde con E2E completo; `docker compose up` levanta el sistema entero; un profesor completa el ciclo de importación sin tocar la terminal.

---

## Mapa de dependencias (simplificado)

```text
F0 Fundaciones
 └─ F1 Manifests/validate ──────────────┐
 └─ F2 Git adapter ──────┐              │
                         ├─ F3 Renderer ─┼─ F4 Preview web
                         │      │        └─ F5 Catálogo
                         │      │
                         │      ├─ F6 Moodle adapter (fake primero)
                         │      │      │
                         │      └──────┴─ F7 Deployment engine
                         │                     │
                         └─────────────────────┴─ F8 Releases/hotfixes
                                                        │
                                                  F9 Export/robustez/entrega
```

- **Pista paralela 🔌 (plugin Moodle):** debe arrancar a la vez que F0. El hito crítico del plugin (tabla + `upsert_book/chapter` + token) debe estar listo **antes de terminar F6** para las pruebas de contrato reales.
- **Camino crítico:** F3 (renderer) y F7 (deployment) son las fases más largas y las que más riesgo concentran (ENG-034/035 y ENG-072 son las tareas a vigilar).

## Milestones sugeridos

| Milestone | Contenido | Demostrable |
|---|---|---|
| **M1** (F0–F4) | validate + preview | Autor escribe y previsualiza con tema |
| **M2** (F5–F6) | catálogo + adapter | Catálogo JSON completo; contrato Moodle verificado contra fake |
| **M3** (F7) | deploy + rollback | Ciclo §32 pasos 5–11 contra Moodle real |
| **M4** (F8–F9) | hotfixes + entrega | Los 13 criterios de aceptación en CI |
