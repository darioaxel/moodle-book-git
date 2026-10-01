# Diagramas de secuencia — Moodle Course as Code (Beta 0.2)

> Diagramas de los flujos funcionales de la Especificación Beta 0.2, en Mermaid
> (se renderizan en GitHub/GitLab/Obsidian/Typora). Actores y participantes:
>
> - **Profesor / Autor / Coordinador / Curadores**: roles humanos (§3 spec).
> - **Plugin Moodle** (`local_courseascode`): páginas UI + web services de escritura.
> - **Engine** (`courseascode-engine`): servicio Python (API + CLI + renderer).
> - **Repo Git**: repositorio de contenidos.
> - **Plataforma Git**: GitHub/GitLab (PRs, checks, webhooks).
> - **Moodle Core**: tablas y APIs estándar de Moodle.

---

## S1. Importación desde el catálogo (profesor desde cero)

Flujo principal del §12 de la spec: el profesor descubre un Book, lo previsualiza
y lo importa a su curso sin tocar Git.

```mermaid
sequenceDiagram
    autonumber
    actor P as Profesor
    participant PL as Plugin Moodle
    participant EN as Engine (API)
    participant GIT as Repo Git
    participant WS as Web Services (plugin)
    participant MC as Moodle Core

    P->>PL: Course as Code → Catálogo
    PL->>EN: GET /catalog
    EN->>GIT: Leer último tag de cada Book
    GIT-->>EN: book.yml + versiones disponibles
    EN-->>PL: Lista de Books importables (solo tags)
    PL-->>P: Catálogo con previews y versiones

    P->>PL: Preview de @dwes/ut03-mvc v1.2.0
    PL->>EN: GET /catalog/@dwes/ut03-mvc/preview?ref=v1.2.0
    EN->>GIT: checkout del tag (worktree aislado)
    EN->>EN: render_book() con PreviewAdapters
    EN-->>PL: HTML renderizado (mismo renderer que producción)
    PL-->>P: Preview con tema

    P->>PL: [Añadir al curso] (v1.2.0, sección 3)
    PL->>EN: POST /deploy {course_id, source, book, ref: v1.2.0}
    Note over EN: Pipeline §17: validate → render → plan → executor
    EN->>GIT: checkout + courseascode validate
    EN->>WS: upsert_book(courseid, título, numbering)
    WS->>MC: Crear Book en sección 3
    loop Por cada capítulo
        EN->>WS: upsert_chapter(bookid, stable_id, título, HTML, posición)
        WS->>MC: Crear capítulo
    end
    loop Por cada asset
        EN->>WS: upload_asset(bookid, archivo)
        WS-->>EN: URL pluginfile.php
    end
    Note over EN: Reescritura de URLs de assets (2ª pasada, ENG-072)
    EN->>WS: register_deploy(source, content_id, version, commit, hash)
    EN-->>PL: DeploymentResult (success)
    PL-->>P: ✓ Publicado @dwes/ut03-mvc v1.2.0
```

---

## S2. Deploy desde CLI (autor técnico)

Mismo pipeline que S1, disparado desde terminal (§17). Incluye plan de despliegue
con confirmación y protección ante borrados (§17.1–17.3).

```mermaid
sequenceDiagram
    autonumber
    actor A as Autor
    participant CLI as courseascode CLI
    participant GIT as Repo Git
    participant WS as Web Services (plugin)
    participant MC as Moodle Core

    A->>CLI: courseascode deploy --course 2026-2027 --book @dwes/ut03-mvc --version 1.2.0
    CLI->>GIT: resolver ref + checkout aislado
    CLI->>CLI: validate (bloqueante si falla)
    CLI->>CLI: render_book() con MoodleAdapters
    CLI->>WS: get_deploy(courseid, source, content_id)
    WS-->>CLI: estado actual (v1.1.0, capítulos, hash)
    CLI->>CLI: Planner → DeploymentPlan
    CLI-->>A: Plan: UPDATE 2 capítulos · CREATE 1 · DELETE 1 · UPLOAD 1 asset

    alt El plan incluye eliminaciones
        CLI-->>A: ⚠ Este despliegue eliminará 1 capítulo [Cancelar/Confirmar]
        A->>CLI: Confirmar despliegue
    else Sin eliminaciones
        CLI-->>A: Continue? [Y/n]
        A->>CLI: Y
    end

    CLI->>WS: upsert_book + upsert/delete_chapter + upload_asset
    WS->>MC: Aplicar cambios
    CLI->>WS: register_deploy(version, commit, content_hash, usuario)
    CLI-->>A: ✓ DeploymentResult (duración, acciones aplicadas)

    Note over A,CLI: Idempotente: repetir el mismo comando produce "sin cambios"
    Note over A,CLI: --yes omite confirmaciones (futuro CI/CD)
```

---

## S3. Detección de actualización y actualización desde Moodle

El profesor ve `UPDATE_AVAILABLE` y actualiza con un clic (§19, §21).

```mermaid
sequenceDiagram
    autonumber
    actor AU as Autor
    participant GH as Plataforma Git
    participant EN as Engine
    participant PL as Plugin Moodle
    actor P as Profesor

    AU->>GH: merge + tag book/ut03-mvc/v1.3.0
    GH->>EN: Webhook (nuevo tag)
    EN->>EN: Recalcular estados de despliegue

    P->>PL: Entra a su curso
    PL->>EN: GET /deployment/status?course_id=...
    EN-->>PL: ut03-mvc: UPDATE_AVAILABLE (severity: normal, disponible: 1.3.0)
    PL-->>P: ↑ Hay una actualización disponible [Ver cambios] [Actualizar]

    P->>PL: [Ver cambios]
    PL->>EN: diff v1.2.0 ↔ v1.3.0
    EN-->>PL: + Observer · ~ MVC · − Introducción histórica
    PL-->>P: Resumen estructural del diff

    P->>PL: [Actualizar]
    Note over PL,EN: Continúa como S1 pasos 9–17 (POST /deploy)
    PL-->>P: ✓ Actualizado a v1.3.0 (mismo Book, sin duplicados)
```

---

## S4. Gobernanza: PR con quórum sobre `main`

Contribución de un profesor a la línea oficial (§10). La gobernanza se ejecuta en
la plataforma Git; el plugin observa y notifica.

```mermaid
sequenceDiagram
    autonumber
    actor J as Juan (autor)
    participant GH as Plataforma Git
    participant CI as Checks CI
    actor C1 as Curadora 1
    actor C2 as Curador 2
    actor CO as Coordinador
    participant EN as Engine
    participant PL as Plugin Moodle

    J->>GH: Push a rama juan + abrir PR → main
    GH->>CI: Ejecutar status checks
    CI->>CI: courseascode validate
    CI->>CI: Check divergencia (capítulos, % líneas, conflictos)
    CI-->>GH: ✓ validate · Tipo: MINOR (quórum: 2)

    GH->>C1: Solicitud de revisión
    GH->>C2: Solicitud de revisión
    Note over GH: El autor no cuenta como votante
    C1->>GH: Approve (1/2)
    C2->>GH: Approve (2/2) — quórum alcanzado

    CO->>GH: Merge (squash) + tag book/ut03-mvc/v1.3.0
    GH->>EN: Webhook (merge + tag)
    EN->>EN: Recalcular estados

    PL-->>J: ✓ Tu propuesta fue aceptada en la oficial v1.3.0
    PL-->>J: Tu rama va 0 commits por detrás [Actualizar mi rama]

    Note over J,PL: Post-beta: panel "Pendiente de tu voto" + recordatorios<br/>y timeout con escalado al coordinador (§10.2)
```

### Variante S4b: PR bloqueado

```mermaid
sequenceDiagram
    autonumber
    actor J as Juan (autor)
    participant GH as Plataforma Git
    participant CI as Checks CI

    J->>GH: PR → main (reescritura completa de UT03)
    GH->>CI: Status checks
    CI-->>GH: ✗ validate OK pero divergencia excesiva<br/>(5/5 capítulos, ~1.900 líneas)
    GH-->>J: PR bloqueado: propón cambios acotados<br/>(máx. ~2 capítulos por PR)
    Note over J: Trocea su contribución en varios PRs pequeños
```

---

## S5. Hotfix crítico

Error grave en una versión desplegada en varios cursos (§11). Forward-fix +
severidad + notificación dirigida; el profesor decide.

```mermaid
sequenceDiagram
    autonumber
    actor CO as Coordinador
    participant GH as Plataforma Git
    participant EN as Engine
    participant PL as Plugin Moodle
    actor P as Profesor (curso afectado)

    Note over CO,GH: v1.3.0 desplegada en 20 cursos; se detecta error grave
    CO->>GH: PR hotfix (carril rápido: 1 aprobación, validate bloqueante)
    GH->>GH: Merge + tag v1.3.1 (forward-fix; v1.3.0 jamás se toca)
    CO->>EN: courseascode release mark v1.3.0<br/>--severity critical --fixed-in v1.3.1 --reason "..."
    EN->>EN: Registrar Release (auditoría) + consulta inversa:<br/>¿qué cursos tienen v1.3.0?

    P->>PL: Entra a su curso
    PL->>EN: GET /deployment/status?course_id=...
    EN-->>PL: UPDATE_AVAILABLE (severity: CRITICAL, fix: 1.3.1)
    PL-->>P: ⚠ ACTUALIZACIÓN CRÍTICA<br/>"El ejemplo contenía SQL inseguro"<br/>[Ver corrección] [Actualizar a 1.3.1] [Actualizar en mis 3 cursos]

    P->>PL: [Actualizar a 1.3.1]
    Note over PL,EN: Pipeline de deploy estándar (S1, pasos 9–17)
    PL-->>P: ✓ Actualizado a v1.3.1

    Note over CO,PL: Nuevos despliegues de v1.3.0 (RECALLED) quedan bloqueados.<br/>Los cursos que no actualicen conservan su contenido: el sistema nunca toca<br/>unilateralmente lo que el alumnado está viendo.
```

---

## S6. Rollback

Volver a una versión anterior = redeploy desde Git (§18). Nunca restauración de
copias de Moodle.

```mermaid
sequenceDiagram
    autonumber
    actor P as Profesor
    participant PL as Plugin Moodle
    participant EN as Engine
    participant GIT as Repo Git
    participant WS as Web Services (plugin)

    P->>PL: Página de versión → [Rollback a v1.0.0]
    PL->>EN: POST /deployment/plan {book, ref: v1.0.0}
    EN->>GIT: checkout tag v1.0.0 + validate
    EN->>EN: Planner (v1.2.0 actual → v1.0.0 objetivo)
    EN-->>PL: Plan (incluye eliminar capítulos añadidos en 1.1/1.2)
    PL-->>P: ⚠ Plan de rollback [Cancelar] [Confirmar]
    P->>PL: Confirmar
    PL->>EN: POST /deploy {ref: v1.0.0}
    EN->>WS: upsert/delete capítulos + register_deploy
    EN-->>PL: DeploymentResult
    PL-->>P: ✓ Book restaurado a v1.0.0 (estado exacto reconstruido desde Git)

    Note over P,WS: Si v1.0.0 estuviera RECALLED: bloqueado salvo --force<br/>(queda en auditoría)
```

---

## S7. Preview local (autor)

Preview = producción: mismo renderer, adapters distintos (§13).

```mermaid
sequenceDiagram
    autonumber
    actor A as Autor
    participant CLI as courseascode CLI
    participant WEB as Servidor preview (FastAPI)
    participant GIT as Repo Git

    A->>CLI: courseascode preview books/ut03-mvc [--ref v1.2.0]
    CLI->>WEB: Arrancar en localhost:3000
    A->>WEB: Abrir capítulo 03-model.md
    WEB->>GIT: Leer archivos (working tree o ref)
    WEB->>WEB: render_book() con PreviewLinkAdapter + PreviewAssetAdapter
    WEB-->>A: HTML con tema (código resaltado, admonitions, enlaces internos)
    loop Edición
        A->>A: Guarda cambios en VS Code
        WEB->>WEB: Watch detecta cambio → re-render
        WEB-->>A: Vista actualizada
    end
```

---

## S8. Detección de drift (edición manual en Moodle)

Un profesor edita el Book a mano; el sistema lo detecta antes de sobrescribir (§19.1).

```mermaid
sequenceDiagram
    autonumber
    actor P as Profesor
    participant MC as Moodle Core
    participant PL as Plugin Moodle
    participant EN as Engine

    P->>MC: Edita un capítulo del Book a mano
    Note over MC: El HTML ya no coincide con content_hash registrado

    P->>PL: [Actualizar a v1.3.0] (días después)
    PL->>EN: POST /deployment/plan
    EN->>PL: (vía get_deploy + HTML actual) comparar hashes
    EN-->>PL: Plan + DRIFT_DETECTED
    PL-->>P: ⚠ Este Book fue modificado manualmente en Moodle.<br/>El despliegue sobrescribirá esos cambios.<br/>[Ver diferencias] [Desplegar de todos modos] [Cancelar]

    alt Desplegar de todos modos
        P->>PL: Confirmar
        Note over PL,EN: Deploy estándar; nuevo content_hash registrado
    else Cancelar
        P->>PL: Cancelar (sin cambios)
    end
```

---

## S9. Export del estado de despliegues

`deployments.yml` como vista exportable para reproducibilidad/auditoría (§9).

```mermaid
sequenceDiagram
    autonumber
    actor CO as Coordinador
    participant CLI as courseascode CLI
    participant WS as Web Services (plugin)
    participant GIT as Repo Git

    CO->>CLI: courseascode export --course 2026-2027
    CLI->>WS: list_deploys(courseid)
    WS-->>CLI: Bindings actuales (source, content_id, version, commit)
    CLI->>CLI: Generar deployments/2026-2027.yml
    CLI-->>CO: Fichero exportado
    CO->>GIT: Commit del export (auditoría histórica)
    Note over CO,GIT: El export es una VISTA; la fuente de verdad del binding<br/>sigue siendo la tabla del plugin
```

---

## S10. Validación como status check en PR

`main` siempre desplegable: la validación corre en CI sobre cada PR (§10.2, §20).

```mermaid
sequenceDiagram
    autonumber
    actor A as Autor
    participant GH as Plataforma Git
    participant CI as Runner CI
    participant EN as courseascode validate

    A->>GH: Push a rama + PR → main
    GH->>CI: Ejecutar checks
    CI->>EN: courseascode validate (checkout del PR)
    alt Validación OK
        EN-->>CI: exit 0
        CI-->>GH: ✓ check verde → PR mergeable (pendiente quórum)
    else Validación fallida
        EN-->>CI: exit 1 + errores localizados
        CI-->>GH: ✗ check rojo → merge bloqueado
        GH-->>A: ✗ 03-model.md — Broken link: 07-ejemplo.md
    end
```

---

## Resumen de correspondencia con la spec v0.2

| Diagrama | Secciones de la spec |
|---|---|
| S1 Importación desde catálogo | §12, §17 |
| S2 Deploy desde CLI | §17, §29 |
| S3 Detección y actualización | §19, §21, §22 |
| S4 Gobernanza PR + quórum | §10, §27 |
| S5 Hotfix crítico | §11 |
| S6 Rollback | §18 |
| S7 Preview local | §13, §14 |
| S8 Drift | §19.1 |
| S9 Export | §9 |
| S10 Validación en PR | §10.2, §20 |
