# Diagramas de secuencia — Acciones del usuario

Un diagrama por cada acción que realizan los usuarios del sistema (autor,
profesor, coordinador) sobre el engine, con el detalle interno relevante.
Formato Mermaid (`sequenceDiagram`). Complementa los diagramas de arquitectura
de [Diagramas de secuencia — Moodle Course as Code](Diagramas%20de%20secuencia%20—%20Moodle%20Course%20as%20Code.md)
y la especificación (§17 pipeline de publicación).

Participantes habituales: **CLI** (`courseascode`), **Servicio** (app FastAPI),
**Pipeline** (`DeploymentService` = validación + render + Planner + Executor),
**Git**, **Moodle** (web services del plugin `local_courseascode` 🔌) y
**BD** (SQLite de releases/auditoría).

## 1. Autor — validar contenido (`courseascode validate [--ref]`)

```mermaid
sequenceDiagram
    actor A as Autor
    participant CLI
    participant V as Validator
    participant G as Git
    A->>CLI: validate [--ref tag/rama]
    alt con --ref
        CLI->>G: checkout_ref(ref) (worktree aislado)
        G-->>CLI: directorio del ref
    end
    CLI->>V: validate(root)
    V->>V: YAML válido · IDs únicos · archivos existen<br/>assets · enlaces .md resolubles · ::: cerrados<br/>metadatos catálogo · numbering
    V-->>CLI: Report (✓/✗ con archivo:línea)
    CLI-->>A: "Validation successful." (exit 0) o errores (exit 1)
```

## 2. Autor — previsualizar (`courseascode preview <book> [--ref]`)

```mermaid
sequenceDiagram
    actor A as Autor
    participant CLI
    participant U as uvicorn
    participant W as App web
    participant R as Renderer único
    participant G as Git
    A->>CLI: preview ut03-mvc [--ref] [--port 3000]
    CLI->>U: run(app, port)
    A->>W: GET /books/ut03-mvc/mvc (navegador)
    opt si ?ref=tag
        W->>G: checkout_ref(ref) por petición
    end
    W->>R: render_book(adapters preview)
    R-->>W: HTML sanitizado + tema
    W-->>A: página (TOC + selector ref/tema)
    Note over A,W: El autor guarda en el editor y refresca:<br/>cada petición re-renderiza sin caché (working tree)<br/>o sirve del RenderCache (tags, clave por sha).
    A->>W: GET /books/ut03-mvc/assets/mvc.svg
    W-->>A: asset (blindado contra path traversal)
```

## 3. Autor — consultar metadata (`courseascode info <book>`)

```mermaid
sequenceDiagram
    actor A as Autor
    participant CLI
    participant R as Renderer
    participant G as Git
    participant VR as VersionResolver
    A->>CLI: info ut03-mvc
    CLI->>G: parse course.yml → book
    CLI->>R: render (contar assets referenciados)
    CLI->>G: get_commit(HEAD)
    CLI->>VR: versions_for(book)
    VR->>G: list_tags("book/ut03-mvc/v*")
    VR-->>CLI: [v1.0.0, v1.1.0, v1.2.0]
    CLI-->>A: ID / Title / Type / Chapters / Assets /<br/>Git commit / Tags (formato §29)
```

## 4. Autor — render a disco (`courseascode build <book>`)

```mermaid
sequenceDiagram
    actor A as Autor
    participant CLI
    participant R as Renderer
    participant T as Tema
    A->>CLI: build ut03-mvc
    CLI->>R: render_book_preview (mismo renderer que producción)
    R-->>CLI: RenderedBook (HTML por capítulo + assets)
    CLI->>T: render_preview_page por capítulo
    CLI->>CLI: escribir build/ut03-mvc/ (index + capítulos + assets)
    CLI-->>A: "Build generado en build/ut03-mvc"
```

## 5. Coordinador/CI — publicar una versión (`courseascode deploy`)

```mermaid
sequenceDiagram
    actor P as Profesor/CI
    participant CLI
    participant S as DeploymentService
    participant G as Git
    participant V as Validator
    participant R as Renderer
    participant M as Moodle 🔌
    participant PL as Planner
    participant E as Executor
    P->>CLI: deploy --course C --book B --version V [--yes]
    CLI->>S: deploy(courseid, book, version)
    S->>S: correlation id (bound_correlation)
    S->>G: resolver ref (latest tag si no hay --version)
    S->>G: checkout_ref + get_commit
    S->>V: validate(checkout) — bloqueante
    S->>R: render pasada 1 (placeholders)
    S->>M: get_course · get_deploy · get_book
    S->>M: upsert_book (si es la primera vez)
    S->>M: upload_asset (solo los que cambian, sha256)
    M-->>S: URLs pluginfile.php
    S->>R: render pasada 2 (URLs reales)
    S->>PL: plan(target) — diff vs HTML actual de Moodle
    PL-->>S: DeploymentPlan (CREATE/UPDATE/DELETE/UPLOAD)
    S-->>CLI: resumen del plan (§17.1)
    alt sin --yes
        P->>CLI: confirmación (y eliminaciones aparte, §17.2)
    end
    CLI->>S: execute
    S->>E: execute(plan, confirmed_deletions)
    E->>M: upsert capítulos (orden del manifest, stable ids)
    E->>M: delete capítulos confirmados · resolver #chapter-<id>
    E->>M: register_deploy (content_hash, commit, actor)
    E-->>S: DeploymentResult
    S-->>CLI: resultado + advertencias
```

## 6. Error a mitad de deploy y recuperación (ENG-102)

```mermaid
sequenceDiagram
    actor P as Profesor/CI
    participant S as DeploymentService
    participant E as Executor
    participant M as Moodle 🔌
    S->>E: execute(plan)
    E->>M: upsert capítulos …
    M--xE: MoodleError (p. ej. timeout)
    E->>M: register_deploy(status="error")
    E--xS: DeploymentExecutionError accionable
    S-->>P: "interrumpido al aplicar UPDATE sobre 'Model': …<br/>Sugerencia: relanza el mismo deploy"
    Note over P,M: El estado del Book es ERROR (§19).<br/>El pipeline es idempotente: no duplica lo ya desplegado.
    P->>S: deploy (idéntico, de nuevo)
    S->>E: execute(plan)
    E->>M: continúa donde falló → register_deploy(ok)
    E-->>S: DeploymentResult(success)
    S-->>P: desplegado; estado UP_TO_DATE
```

## 7. Profesor — importar un Book desde el catálogo (Moodle 🔌 → servicio)

```mermaid
sequenceDiagram
    actor T as Profesor
    participant UI as Plugin Moodle 🔌
    participant S as Servicio (FastAPI)
    participant CB as CatalogBuilder
    participant G as Git
    T->>UI: Curso → Course as Code → Catálogo
    UI->>S: GET /catalog (identidad del llamante)
    S->>CB: build() — último tag de cada Book, solo tags (nunca HEAD)
    CB->>G: list_tags + checkout por Book
    CB-->>S: entries (título, summary, capítulos, versiones)
    S-->>UI: JSON del catálogo visible (ACL por fuente)
    UI-->>T: tarjetas @dwes/ut03-mvc v1.2.0 · [Preview] [Añadir al curso]
    T->>UI: Añadir al curso (versión fijada + sección)
    UI->>S: POST /deploy {course_id, source, book_id, ref}
    S-->>UI: pipeline completo (diagrama 5)
    UI-->>T: Book creado en la sección elegida
```

## 8. Profesor — actualizar a una versión nueva (UPDATE_AVAILABLE → publicar)

```mermaid
sequenceDiagram
    actor T as Profesor
    participant UI as Plugin Moodle 🔌
    participant S as Servicio
    participant G as Git
    participant M as Moodle 🔌
    T->>UI: Panel del curso
    UI->>S: GET /deployment/status?course_id=C
    S->>G: latest(book) → v1.2.0
    S->>M: get_deploy(C, source, book)
    S-->>UI: UPDATE_AVAILABLE (badge severidad si la hay)
    UI-->>T: "@dwes/ut03-mvc · desplegada 1.1.0 · disponible 1.2.0"
    T->>UI: Ver plan de cambios
    UI->>S: POST /deployment/plan {…ref=v1.2.0}
    S-->>UI: plan §17.1 (~ 02-mvc.md · + 05-controller.md …)
    UI-->>T: Changes + Moodle actions
    T->>UI: Publicar
    UI->>S: POST /deploy {…, ref=v1.2.0}
    S->>M: upsert sobre el MISMO Book (sin duplicados, §17.3)
    S-->>UI: resultado
    UI-->>T: "Actualizado a v1.2.0"
```

## 9. Profesor — rollback a una versión anterior

```mermaid
sequenceDiagram
    actor T as Profesor
    participant UI as Plugin Moodle 🔌
    participant S as Servicio
    T->>UI: Rollback a… → elegir v1.0.0
    UI->>S: POST /deploy {course_id, source, book_id, ref=book/…/v1.0.0}
    Note over S: Rollback = deploy de una versión anterior:<br/>mismo pipeline (§18), sin código especial.
    S-->>UI: resultado (estado exacto de v1.0.0,<br/>content_hash idéntico al deploy original)
    UI-->>T: "Book restaurado a v1.0.0"
```

## 10. Coordinador — marcar severidad / recall (hotfix crítico §11.1)

```mermaid
sequenceDiagram
    actor C as Coordinador
    participant CLI
    participant DB as SQLite (releases + auditoría)
    participant S as Servicio
    participant M as Moodle 🔌
    C->>CLI: release mark book/ut03-mvc/v1.3.0<br/>--severity critical --fixed-in v1.3.1 --reason "…"
    CLI->>CLI: exige COURSEASCODE_ADMIN_TOKEN (rol coordinador)
    CLI->>DB: mark (upsert por ref: severity, recall, fixed_in, reason)
    DB->>DB: AuditEvent "release.mark" (quién/cuándo/qué)
    CLI-->>C: "book/ut03-mvc/v1.3.0 marcado: critical"
    C->>S: (el servicio lo consulta al planear/estado)
    S->>DB: severity_of / is_recalled
    Note over C,M: DoD: status muestra badge crítico;<br/>deploy de la RECALLED falla (salvo --force, con warning);<br/>GET /releases/affected lista cursos + profesores<br/>(la notificación la envía el plugin 🔌).
```

## 11. Sistema — webhook de Git (push/tag → recálculo)

```mermaid
sequenceDiagram
    participant GP as Plataforma Git
    participant S as Servicio
    participant DB as SQLite
    participant C as RenderCache
    GP->>S: POST /hooks/git (body: push/merge/tag)
    S->>S: verifica firma HMAC-SHA256<br/>(X-CourseAsCode-Signature: sha256=<hex>)
    alt firma inválida
        S-->>GP: 401
    else firma válida
        S->>DB: AuditEvent "webhook.git"
        S->>C: clear() (invalidación conservadora)
        S-->>GP: 200 {evento procesado}
        Note over S: Las cachés de checkouts/renders se recalculan<br/>bajo demanda; hoy no-op más allá de la invalidación<br/>(recálculo proactivo: post-Beta).
    end
```

## 12. Coordinador — auditoría y exportación

```mermaid
sequenceDiagram
    actor C as Coordinador
    participant CLI
    participant M as Moodle 🔌
    participant DB as SQLite
    C->>CLI: status --course C
    CLI->>M: list_deploys(courseid) · get_deploy por book
    CLI->>DB: severity_of (badge crítico)
    CLI-->>C: tabla Book / Version / State / Severity / Commit
    C->>S: GET /audit?book_id=… (X-CourseAsCode-Admin-Token)
    S->>DB: audit()
    S-->>C: deploys · release.mark · webhook.git (append-only)
    C->>CLI: export --course C
    CLI->>M: list_deploys(courseid)
    CLI->>CLI: deployments/<curso>.yml (vista exportable, §9)
    CLI-->>C: ruta del fichero (bytes estables)
```

---

Notas transversales:

- **Renderer único (principio 5):** los diagramas 2, 4, 5 y 7–9 usan el mismo
  `render_book`; solo cambian los adapters de enlaces/assets (preview local vs
  Moodle `pluginfile.php`).
- **Idempotencia (§17.3):** todo camino de escritura clave por stable ids
  (capítulos) y por `(courseid, source, content_id)` (books y registros).
- Los pasos marcados 🔌 (plugin) son la pista paralela: el engine ya consume su
  contrato (`moodle/functions.py`) y lo simula con `FakeMoodleProvider` en CI.
