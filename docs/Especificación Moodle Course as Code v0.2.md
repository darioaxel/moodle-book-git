# Moodle Course as Code — Especificación Beta 0.2

> Versión 0.2 del documento de especificación. Sustituye a la Beta 0.1.
> Esta versión consolida las decisiones de diseño tomadas sobre: arquitectura
> híbrida, catálogo e importación por referencia, modelo de ramas con
> gobernanza colegiada, ciclo de vida de versiones con hotfixes, y privacidad.

---

## 0. Registro de cambios 0.1 → 0.2

| Decisión | Resumen |
|---|---|
| Arquitectura | Se fija como **híbrida**: servicio Python (motor) + plugin Moodle `local_courseascode` (puerta de entrada). Eliminada la ambigüedad Python/PHP del §4 original. |
| Importación | Se añade el **catálogo en Moodle** y el modelo de importación **por referencia** (gestor de paquetes). Importar ≠ copiar. |
| Fuente de verdad del despliegue | El binding curso↔versión vive en la **tabla del plugin**; `deployments.yml` pasa a ser vista exportable. Reformulado el §10 original. |
| Identidad | La identidad del contenido pasa a ser `(source, id, version)` con namespaces (`@dwes`, `@juan`). |
| Ramas y gobernanza | Repo único por curso; `main` protegida; escritura solo vía **PR con quórum** del consejo de curadores; ramas personales libres. |
| Ciclo de vida | Estados DRAFT → RELEASED → SUPERSEDED → RECALLED; hotfixes con *forward-fix* y notificación dirigida. |
| Privacidad | Repo privado; se documenta que Git no permite lectura por rama; fork privado opt-in; metadata Git solo para profesores. |
| Detalles técnicos | Resaltado Pygments con estilos inline; reescritura de URLs de assets; detección de drift; flag `--yes`; comportamiento en backup/restore. |

---

## 1. Objetivo

Desarrollar una primera versión funcional de un sistema denominado provisionalmente **Moodle Course as Code**, cuyo objetivo final es permitir definir un curso Moodle mediante archivos versionados en Git y utilizar Moodle como plataforma de despliegue.

La arquitectura debe diseñarse desde el principio para evolucionar desde **Books** hacia Pages, Quizzes, Assignments, Resources, estructura de cursos, configuración de actividades, metadatos curriculares y releases de cursos.

**La Beta 0.2 SOLO implementa Books.**

Principio fundamental:

> Git es la fuente de verdad del **contenido docente**. Moodle es la plataforma de publicación y ejecución.

Moodle nunca se convierte en el editor principal del contenido.

---

## 2. Alcance funcional de la Beta

El sistema debe permitir este flujo completo:

```text
Autor → Markdown → Git (historial, ramas, tags, PRs)
     → Manifest → Validate → Preview → Deploy
     → Moodle Book → Alumnado
     → Detección de nuevas versiones → Actualización → Rollback
     → Hotfix crítico → Notificación dirigida
```

El usuario debe poder:

1. Crear un Book mediante Markdown organizado en capítulos.
2. Ver una previsualización HTML fiel antes de publicar.
3. Utilizar un estilo visual propio (tema).
4. Versionar el contenido con Git (tags semánticos).
5. **Descubrir contenidos disponibles desde un catálogo dentro de Moodle.**
6. **Importar un Book a su curso por referencia (sin copiar contenido).**
7. Definir qué versión se publica en cada curso.
8. Publicar/sincronizar el Book con Moodle.
9. Ver desde Moodle qué versión está publicada (solo profesores).
10. Ver desde Moodle si hay actualizaciones disponibles y su severidad.
11. Actualizar el Book a una nueva versión.
12. Volver a desplegar una versión anterior (rollback).
13. Personalizar contenido en una rama propia y desplegarla (vía CLI).
14. Proponer mejoras a la línea oficial mediante PR con aprobación colegiada.

---

## 3. Roles

El sistema distingue cuatro roles:

| Rol | Descripción | Herramientas |
|---|---|---|
| **Autor** | Crea o modifica contenido | VS Code + Git + CLI (post-beta: editor web) |
| **Profesor-consumidor** | Importa y publica contenido sin modificarlo | Moodle (catálogo, botones) |
| **Consejo de curadores** | Profesores de la asignatura que revisan y aprueban PRs a `main` | Plataforma Git + panel en Moodle |
| **Coordinador** | Desempata, gestiona releases, declara severidad | CLI + plataforma Git |

Un mismo usuario puede ejercer varios roles. El alumnado no es un rol del sistema: solo consume el Book publicado en Moodle.

---

## 4. Principios de diseño

1. **Git es la fuente de verdad del contenido.** Moodle nunca es la fuente maestra.
2. **Versiones inmutables.** Un tag publicado jamás se mueve ni se corrige in situ.
3. **Despliegues reproducibles.** Dado repositorio + commit + curso, se puede reconstruir exactamente el estado del Book.
4. **IDs estables.** Nunca se usan títulos como identificadores.
5. **Preview = producción.** La preview usa exactamente el mismo renderer que el despliegue. Existe UN solo renderer.
6. **Idempotencia.** Ejecutar dos veces el mismo despliegue produce el mismo estado; no crea duplicados.
7. **Importar = vincular, no copiar.** Los cursos referencian versiones; nunca bifurcan contenido silenciosamente.
8. **La gobernanza se ejecuta en la plataforma Git; el plugin observa y notifica.** El plugin nunca parsea Markdown, nunca toca Git, nunca decide planes de despliegue.
9. **Nada se borra silenciosamente.** Toda eliminación se detecta, se registra y requiere confirmación.
10. **El profesor decide.** El sistema nunca cambia unilateralmente el contenido que el alumnado está viendo.
11. **Preparado para nuevos recursos.** Book, Page, Quiz, Assignment, Resource sin rehacer el núcleo.

---

## 5. Arquitectura general

### 5.1. Las tres piezas

```text
┌──────────────────┐      ┌─────────────────────────────┐      ┌──────────────────────────┐
│   GIT (verdad)   │      │   SERVICIO PYTHON           │      │   MOODLE                 │
│                  │      │   "courseascode-engine"     │      │                          │
│  dwes-content/   │◄─────│                             │      │  ┌────────────────────┐  │
│   course.yml     │ read │  · Content Engine           │─────►│  │ plugin             │  │
│   books/...      │      │  · Git Adapter              │  WS  │  │ local_courseascode │  │
│   ramas y tags   │      │  · Renderer + Theme         │ REST │  │  · tabla propia    │  │
└──────────────────┘      │  · Deployment Engine        │      │  │  · web services    │  │
                          │  · Catalog API              │      │  │    de escritura    │  │
       ▲                  │  · CLI + Preview web        │      │  │  · páginas UI      │  │
       │                  └─────────────────────────────┘      │  └────────────────────┘  │
       │                                ▲                     └──────────────────────────┘
   Autor (Markdown,                     │ HTTP                        ▲
   tags, CLI) ◄─────────────────────────┘                             │
                                       Profesor (catálogo, importar, actualizar, votar)
```

**Regla de oro:** toda la lógica vive en el servicio Python. El plugin Moodle es deliberadamente "tonto": expone operaciones atómicas (crear capítulo, subir archivo, registrar despliegue) y pinta pantallas. Esto garantiza renderer único (principio 5) y desacopla Moodle de Git (principio 8).

### 5.2. Servicio Python `courseascode-engine`

Un único paquete Python consumido de tres maneras: **CLI**, **servidor de preview local** y **API HTTP** para el plugin Moodle.

```text
courseascode/
├── domain/          # Course, Book, Chapter, Version, DeploymentPlan, DeploymentResult
│                    # (modelos puros: sin dependencias de Git ni de Moodle)
├── manifests/       # parseo y validación de course.yml / book.yml (PyYAML + pydantic)
├── git/             # GitProvider (interfaz) + LocalGitProvider (GitPython)
│                    # get_ref, checkout_ref, list_tags(pattern), diff(ref_a, ref_b)
├── content/         # parser Markdown (CommonMark + tablas + admonitions),
│                    # renderer (Jinja2 + theme), Pygments con estilos INLINE,
│                    # link_resolver, asset_resolver
├── catalog/         # construye el catálogo recorriendo books + tags del repo;
│                    # registro de fuentes con ACL (visibilidad por propietario)
├── deployment/      # planner: diff (estado Moodle vs target) → DeploymentPlan
│                    # executor: aplica el plan de forma idempotente vía MoodleProvider
├── moodle/          # MoodleProvider (interfaz) + MoodleRestClient (httpx, token)
├── api/             # FastAPI: endpoints que consume el plugin Moodle
├── web/             # preview local (reutiliza el mismo renderer)
└── cli/             # Typer: validate, preview, info, build, deploy, status, release
```

### 5.3. Plugin Moodle `local_courseascode`

Cuatro responsabilidades, ninguna con lógica de negocio:

**a) Tabla propia** (`db/install.xml`):

```text
local_courseascode_deploy
  id, courseid, bookid,
  source,               -- fuente (repo/rama): p.ej. "main", "juan", URL de fork
  content_id,           -- p.ej. "ut03-mvc"
  content_version,      -- p.ej. "1.3.0" o "1.3.0+juan.4"
  git_ref, git_commit,
  content_hash,         -- hash del HTML desplegado (detección de drift)
  deployed_at, deployed_by, status
```

**b) Web services de escritura** (`db/services.php` + `externallib.php`). Moodle core NO ofrece escritura sobre Books; el plugin expone operaciones atómicas:

```text
local_courseascode_upsert_book(courseid, name, intro, numbering) → bookid
local_courseascode_upsert_chapter(bookid, chapter_stable_id, title, content_html, position)
local_courseascode_delete_chapter(bookid, chapter_stable_id)
local_courseascode_upload_asset(bookid, filename, data) → pluginfile URL
local_courseascode_register_deploy(...)
local_courseascode_get_deploy(courseid, content_id)
```

Los capítulos se identifican por su `id` estable del `book.yml`, no por el id interno de Moodle. Esto es lo que hace posible la idempotencia.

**c) Páginas de interfaz** (PHP + plantillas Mustache, llamando server-to-server al servicio):

- **Catálogo** (`/local/courseascode/catalog.php`) — descubrimiento e importación.
- **Página de versión** por Book.
- **Panel de administración** del curso: estado de todos los Books, acciones Preview/Compare/Deploy.

**d) Integraciones obligatorias:**

- Capabilities: `local/courseascode:viewcatalog`, `:deploy`, `:manage`. Las páginas del plugin son **solo para profesores**; el alumnado ve únicamente el Book renderizado.
- Inyección del CSS del tema en las páginas del Book.
- Comportamiento definido en backup/restore (§28).
- Cuenta técnica + token con las mínimas capabilities; credenciales por variables de entorno.

### 5.4. Contrato servicio → plugin (API HTTP del servicio)

```text
GET  /catalog                            → books importables (último tag de cada fuente visible)
GET  /catalog/{source}/{book}/versions   → versiones disponibles
GET  /catalog/{source}/{book}/preview?ref=
POST /deploy                             → { course_id, source, book_id, ref } → pipeline completo
POST /deployment/plan                    → plan de cambios sin ejecutar
GET  /deployment/status?course_id=       → estados: UP_TO_DATE / UPDATE_AVAILABLE (+severity) / ...
GET  /deployment/where?source=&book=&version=  → consulta inversa: cursos afectados
```

Moodle nunca consulta Git directamente: cuando necesita saber si hay `UPDATE_AVAILABLE`, pregunta al servicio.

---

## 6. Repositorio de contenidos

Un repositorio por curso/departamento:

```text
dwes-content/
│
├── course.yml
│
├── books/
│   └── ut03-mvc/
│       ├── book.yml
│       ├── 01-introduccion.md
│       ├── 02-mvc.md
│       ├── 03-model.md
│       ├── 04-view.md
│       ├── 05-controller.md
│       └── assets/
│           ├── mvc.svg
│           └── ejemplo.png
│
└── README.md
```

**Regla de contenido:** el repositorio contiene únicamente material **publicable ante alumnos**. Exámenes, soluciones y bancos de preguntas NO viven aquí (ver §26).

### 6.1. Manifest del curso (`course.yml`)

```yaml
id: dwes
title: Desarrollo Web en Entorno Servidor

books:
  - id: ut03-mvc
    path: books/ut03-mvc
```

En futuras versiones podrá contener `pages:`, `quizzes:`, `assignments:`, `resources:`. En Beta solo `books`.

### 6.2. Manifest del Book (`book.yml`)

```yaml
id: ut03-mvc
type: book

title: MVC y patrones de diseño

description: >
  Introducción al patrón MVC y su aplicación
  en aplicaciones web.

# Metadatos de catálogo (obligatorios para que el Book sea importable)
summary: >
  Introducción al patrón MVC y su aplicación
  en aplicaciones web con PHP.
tags: [php, patrones, arquitectura]
audience: 2º DAW · DWES
cover: assets/cover.png        # opcional

numbering: numbers             # opción del Book Moodle: none | numbers | bullets | indented

chapters:
  - id: introduccion
    title: Introducción
    file: 01-introduccion.md
  - id: mvc
    title: MVC
    file: 02-mvc.md
  - id: model
    title: Model
    file: 03-model.md
  - id: view
    title: View
    file: 04-view.md
  - id: controller
    title: Controller
    file: 05-controller.md
```

- El `id` es estable: puede cambiar el título o la posición, nunca el id conceptual.
- **No hay campo `version` en book.yml** (eliminado respecto a 0.1): la versión la define el tag Git, evitando la doble fuente de verdad.

---

## 7. Identidad del contenido

La identidad completa de un contenido desplegado es la tripleta:

```text
(source, id, version)

main/ut03-mvc  @ v1.3.0       ← línea oficial
juan/ut03-mvc  @ 1.3.0+juan.4 ← línea personal de Juan
```

- `source` identifica el origen: rama del repo compartido (`main`, `juan`) o URL de un fork privado.
- Los namespaces se muestran como `@dwes/ut03-mvc` (oficial), `@juan/ut03-mvc` (personal).
- Nunca se usa el título como identificador, ni de Books ni de capítulos.

---

## 8. Versionado

Git como sistema real de versionado (no como backup).

### 8.1. Línea oficial

Tags semánticos `MAJOR.MINOR.PATCH` con el patrón:

```text
book/ut03-mvc/v1.0.0
book/ut03-mvc/v1.1.0
book/ut03-mvc/v1.2.0
```

Reglas:

- **PATCH**: correcciones menores.
- **MINOR**: contenido nuevo compatible.
- **MAJOR**: cambios estructurales o pedagógicos importantes.

El sistema puede **sugerir** el tipo de bump analizando el diff del PR (capítulos nuevos → MINOR; solo correcciones → PATCH); decide el consejo.

### 8.2. Versiones de ramas personales

Las ramas personales no gestionan números de versión a mano. Su versión se **calcula** como semver con metadatos de derivación:

```text
1.2.0+juan.3   →  "basado en la oficial v1.2.0, con 3 commits propios"
```

(tag oficial base + commits ahead). En la página de versión se muestra: *"Basado en la versión oficial 1.2.0 · 3 cambios propios"*.

### 8.3. Inmutabilidad

Una versión publicada mediante tag es inmutable. Los errores se corrigen con una versión nueva (§11), jamás moviendo el tag.

---

## 9. Release y deployment: dónde vive el binding

**Versión de contenido ≠ despliegue en Moodle.** Un Book puede existir en Git en v1.0.0…v2.0.0, y cada curso usa la versión que decida su profesor:

```text
Curso DWES 2025-2026 → ut03-mvc @ v1.1.0
Curso DWES 2026-2027 → ut03-mvc @ v1.2.0
```

**Decisión (cambio respecto a 0.1):** el binding curso↔versión vive en la **tabla del plugin** (`local_courseascode_deploy`), porque las importaciones se realizan desde la interfaz de Moodle sin tocar Git.

- El fichero `deployments/2026-2027.yml` pasa a ser una **vista exportable** (comando `courseascode export`) para reproducibilidad y auditoría, no la fuente de verdad.
- Git sigue siendo la fuente de verdad **del contenido**; la asignación curso↔versión es configuración de despliegue.
- Post-beta podrá existir un modo `managed_by: git` para perfiles técnicos que prefieran gestionar despliegues desde el repo (un solo escritor por despliegue, nunca dos simultáneos).

### 9.1. Identificación del curso Moodle

El despliegue identifica el curso por su `courseid` real de Moodle (resoluble por `idnumber`). El alias legible (`dwes 2026-2027`) se mapea en la configuración del plugin.

---

## 10. Modelo de ramas y gobernanza

### 10.1. Estructura

```text
dwes-content (repo único, PRIVADO)
│
├── main          ← línea oficial, PROTEGIDA, curada por el consejo
│     └── tags: book/ut03-mvc/v1.2.0, v1.3.0...
│
├── juan          ← rama personal de Juan (libre)
└── maria         ← rama personal de María (libre)
```

- **Repo único por curso**, privado (§26).
- **Las ramas personales son territorio libre**: nadie vota lo que Juan hace en su rama para su alumnado.
- **La divergencia limita las contribuciones a `main`, nunca el uso personal.**

### 10.2. Escritura en `main`: solo por PR con quórum

`main` es rama protegida: **ningún push directo**; todo cambio entra por pull request aprobado por el **consejo de curadores** (los profesores de la asignatura, típicamente 3–6 personas — no votación abierta universal). El autor nunca cuenta como votante de su propio PR.

Quórum graduado por tipo de cambio (sugerido automáticamente a partir del diff):

| Tipo | Ejemplo | Quórum | Reglas extra |
|---|---|---|---|
| PATCH | Errata, ejemplo corregido | 1 visto bueno | Rápido por definición |
| MINOR | Capítulo nuevo | 2 vistos buenos | Estándar |
| MAJOR | Reestructurar la unidad | 2 vistos buenos + **ventana de discusión** (p. ej. 5 días) | Nadie puede alegar desconocimiento |
| Hotfix crítico | Error grave en producción | 1 visto bueno + **aviso retroactivo** a todo el consejo | La velocidad manda (§11) |

**Checks automáticos obligatorios en todo PR a `main`:**

1. `courseascode validate` — **bloqueante**. `main` debe poder desplegarse siempre.
2. **Check de divergencia** — mide el tamaño del cambio (capítulos tocados, % de líneas, conflictos) y emite veredicto. Umbrales configurables (referencia: máx. ~30% de líneas de un Book, máx. ~2 capítulos por MR). Las contribuciones grandes se trocean en PRs acotados.

**Merge ≠ release.** Tras el merge, el coordinador (o el consejo) crea el tag oficial. Sin tag, no hay versión importable.

**Reglas anti-bloqueo:**

- Timeout de quórum: si un PR MINOR lleva 7 días sin votos, escala con recordatorios; en última instancia decide el coordinador.
- **Nunca auto-merge por silencio.**
- Empate o veto argumentado: discusión en el PR; desempata el coordinador.
- Métrica de salud: tiempo medio de aprobación visible en el panel.

### 10.3. Implementación de la gobernanza

**No se construye un sistema de votación propio.** Se configura con lo que ya ofrece la plataforma Git:

- GitHub: branch protection + *required approving reviews: N* + `CODEOWNERS` (equipo del curso) + *dismiss stale approvals*.
- GitLab: approval rules con N aprobaciones y grupo de aprobadores.

Requisito de infraestructura: plataforma Git con ramas protegidas, MRs y webhooks (GitHub/GitLab). El `LocalGitProvider` queda para desarrollo y escenarios mono-autor.

### 10.4. Notificaciones

Webhook de la plataforma Git → el servicio recalcula estados → el plugin muestra en Moodle:

- Al autor: *"Tu propuesta para UT03 fue aceptada en la oficial v1.3.0"*.
- A todos los afectados: *"Tu rama va 2 commits por detrás de la oficial"* con [Ver cambios].
- Post-beta: panel **"Pendiente de tu voto"** con los PRs abiertos que requieren revisión del usuario.

La actualización de la rama personal (`main → juan`) la ejecuta el propio profesor (Git; post-beta: asistida desde el editor). Si los cambios aceptados eran suyos, el merge suele ser limpio; los conflictos llegan de cambios de terceros sobre los mismos capítulos.

**Recomendación pedagógica documentada:** personalización *aditiva* siempre que sea posible (añadir capítulos propios en lugar de editar los oficiales) para minimizar conflictos futuros.

---

## 11. Ciclo de vida de una versión

```text
DRAFT → RELEASED → SUPERSEDED → (opcional) RECALLED
 rama     tag        hay una       retirada por
 sin tag  publicado   más nueva     error grave
```

- **RELEASED**: importable desde el catálogo y desplegable.
- **SUPERSEDED**: sigue desplegable y reproducible; el catálogo muestra la nueva por defecto.
- **RECALLED**: bloqueada para nuevos despliegues e importaciones. Los cursos que ya la tienen reciben aviso crítico; **no se les cambia nada automáticamente**.

La severidad y el recall son **estado administrativo mutable** gestionado por el servicio (con auditoría completa), no por Git.

### 11.1. Flujo de hotfix crítico

Escenario: v1.3.0 está desplegada en 20 cursos y se detecta un error grave.

1. **Nunca se corrige el pasado**: se publica `v1.3.1` (PATCH) con *solo* la corrección. *Forward-fix*, siempre.
2. PR de hotfix con carril rápido: 1 aprobación, pero `validate` sigue siendo bloqueante.
3. Merge + tag inmediato (no se espera a agrupar cambios).
4. El coordinador declara la severidad:

```bash
courseascode release mark book/ut03-mvc/v1.3.0 \
  --severity critical \
  --fixed-in v1.3.1 \
  --reason "El ejemplo del patrón Active Record contenía SQL inseguro"
```

5. Webhook → el servicio recalcula. Gracias a la consulta inversa (`/deployment/where`), el sistema **sabe exactamente qué cursos están afectados**.
6. **Notificación dirigida** (no genérica) a los profesores de esos cursos:

```text
⚠ ACTUALIZACIÓN CRÍTICA — UT03 · MVC y patrones de diseño

Tu versión (1.3.0) contiene un error corregido en 1.3.1:
"El ejemplo del patrón Active Record contenía SQL inseguro"

[Ver corrección]  [Actualizar a 1.3.1]  [Actualizar en mis 3 cursos]
```

7. **El profesor decide y ejecuta** (un clic = redeploy idempotente). Las ramas personales basadas en 1.3.0 también reciben aviso ("tu versión base oficial tiene un hotfix disponible").

**Decisión:** no hay auto-actualización en Beta. Si la institución la quiere, será una política configurable explícita (p. ej. aplicar hotfixes críticos a las 72 h), nunca el comportamiento por defecto.

El deploy engine **bloquea nuevos despliegues de versiones RECALLED** (`--force` documentado para casos excepcionales).

---

## 12. Catálogo e importación

### 12.1. Modelo mental: gestor de paquetes

| Gestor de paquetes | Course as Code |
|---|---|
| Registry | Catálogo de contenidos |
| Paquete | Book (`@dwes/ut03-mvc`) |
| Versión | Tag Git |
| `package.json` | Binding del curso (tabla del plugin) |
| `install` | Importar → deploy |
| "hay versión nueva" | `UPDATE_AVAILABLE` |

**Importar no es copiar contenido a Moodle: es declarar una dependencia** ("este curso usa `@dwes/ut03-mvc` en la versión X"). El contenido sigue en Git; Moodle guarda la referencia. Así, cuando el departamento publica v1.3.0, todos los cursos vinculados ven `UPDATE_AVAILABLE`.

### 12.2. El catálogo vive dentro de Moodle

El profesor trabaja en Moodle, no en Git. Página del plugin: **Curso → Course as Code → Catálogo**.

```text
┌────────────────────────────────────────────────────────┐
│ @dwes/ut03-mvc · MVC y patrones de diseño              │
│ Introducción al patrón MVC y su aplicación en web.     │
│ Última versión: 1.2.0 · 5 capítulos                    │
│ [Preview]                    [Añadir al curso ▾ v1.2.0]│
├────────────────────────────────────────────────────────┤
│ @dwes/ut04-dao · Capa de acceso a datos                │
│ ...                                                    │
└────────────────────────────────────────────────────────┘
```

- El catálogo se **deriva** de los `book.yml` del repo en el último tag de cada Book (no hay `catalog.yml` aparte que mantener).
- **Solo muestra versiones taggeadas** (releases), nunca HEAD ni trabajo en progreso.
- Fuentes múltiples con ACL: cada profesor ve la oficial (`@dwes`) y las suyas (`@juan`). En Beta: una única fuente oficial.
- El **Preview** usa exactamente el mismo renderer que el despliegue (principio 5).

### 12.3. Flujo de importación (profesor desde cero)

1. Entra a su curso Moodle vacío → **Course as Code → Catálogo**.
2. Navega los Books disponibles; puede previsualizar cualquiera.
3. **Añadir al curso** → elige **versión** (por defecto el último tag; siempre fijada, no hay "track latest") y **sección del curso**.
4. El plugin llama a `POST /deploy` y el servicio ejecuta el pipeline completo (§17).
5. El Book aparece en la sección elegida, registrado en la tabla del plugin.

A partir de ahí funcionan la página de versión, `UPDATE_AVAILABLE`, actualización y rollback.

**Permisos:** importar requiere `moodle/course:manageactivities` + `local/courseascode:deploy`.

**Queda fuera de la Beta:** plantillas de curso completo (importar un `course.yml` entero de un clic), búsqueda avanzada, valoraciones, "track latest".

---

## 13. Preview

La preview se ofrece en tres contextos, **todos con el mismo renderer**:

1. **CLI**: `courseascode preview books/ut03-mvc` → servidor local `http://localhost:3000`.
2. **Catálogo en Moodle**: antes de importar.
3. **Panel de administración**: preview de una versión candidata antes de actualizar.

```text
Content Renderer
       │
       ├── Preview adapter (local)
       ├── Preview adapter (catálogo Moodle)
       └── Moodle adapter (despliegue)
```

Está prohibido crear un "renderer preview" y un "renderer Moodle" separados.

La preview muestra el contenido con el **tema propio** del sistema (§14). Se documenta que el tema de Moodle aplicará su propio CSS alrededor del Book; el objetivo de la preview es fidelidad del *contenido renderizado* (tipografía, admonitions, código, tablas), no una réplica pixel-perfect del tema del campus.

---

## 14. Renderer y sistema de temas

Pipeline:

```text
Markdown → AST (CommonMark) → HTML semántico → Theme → Preview/Moodle
```

- El estilo nunca se mezcla con el Markdown. El contenido no contiene clases CSS del tema.
- Temas previstos: `theme-default`, `theme-dwes`, `theme-centro`.
- **Resaltado de sintaxis**: Pygments con `noclasses=True` (estilos **inline**). Motivo: el tema de Moodle no incluye el CSS de Pygments; con clases, el código se vería sin colores en Moodle y coloreado en preview, violando el principio 5.

### 14.1. Componentes Markdown soportados (mínimo Beta)

Títulos H1–H6, párrafos, negrita, cursiva, enlaces, listas, listas numeradas, tablas, blockquotes, código inline, bloques de código con resaltado, imágenes, separadores horizontales, enlaces internos (§16) y **admonitions**.

Sintaxis de admonitions (vía plugin `container` de markdown-it):

```markdown
:::note
Recuerda que MVC separa responsabilidades.
:::
```

Tipos iniciales: `note`, `warning`, `tip`, `important`. Su renderizado en Moodle usa el marcado semántico del tema (compatible con los estilos que el plugin inyecta).

### 14.2. Sanitización

El renderer aplica una política explícita de HTML permitido: nada de `<script>` ni eventos HTML (`on*`). El Markdown no puede ejecutar JavaScript arbitrario.

---

## 15. Imágenes y assets

Los assets forman parte del repositorio y se referencian con rutas relativas:

```markdown
![Arquitectura MVC](assets/mvc.svg)
```

Pipeline de despliegue:

```text
Git → checkout del tag → assets → upload vía Files API (plugin) → pluginfile URL
```

**Reescritura de URLs (obligatoria):** en el HTML renderizado, cada referencia `assets/...` se reescribe a la URL `pluginfile.php/...` que Moodle asigna al subir el archivo. Es el mismo patrón que el resolver de enlaces internos (§16).

- No se depende de URLs externas para assets locales.
- Los assets se suben por Book y se referencian por nombre de archivo; el executor es idempotente (re-subir el mismo asset no duplica).

---

## 16. Enlaces internos

Soporte de enlaces entre capítulos en sintaxis Markdown natural:

```markdown
[Ver Model](03-model.md)
```

Capa de resolución durante el renderizado:

```text
source link (03-model.md) → content resolver → URL del capítulo en Moodle
```

- Nunca quedan apuntando a `03-model.md` dentro de Moodle.
- El resolver falla en `validate` si el destino no existe (enlace roto = validación fallida = no se puede publicar).
- Los enlaces a anclas dentro del mismo capítulo (`#seccion`) se preservan.

---

## 17. Publicación

La acción **PUBLICAR** (desde CLI o desde el botón en Moodle — mismo código) ejecuta:

```text
1. Resolver el git_ref (tag, rama o commit)
2. Checkout del contenido
3. Validar manifests (course.yml, book.yml)
4. Validar todos los capítulos
5. Resolver assets
6. Renderizar Markdown (mismo renderer que preview)
7. Reescritura de enlaces internos y URLs de assets
8. Generar DeploymentPlan (diff vs estado actual en Moodle)
9. [Confirmación del usuario, salvo --yes]
10. Ejecutar plan: upsert Book, upsert capítulos, borrar capítulos confirmados,
    subir assets
11. Registrar en la tabla: source, content_id, versión, commit, fecha, usuario,
    content_hash
12. Devolver DeploymentResult
```

### 17.1. Deployment plan (antes de tocar Moodle)

```text
Deployment plan

Course:  DWES 2026-2027
Book:    @dwes/ut03-mvc
Current: 1.1.0
Target:  1.2.0

Changes:
  ~ 02-mvc.md
  ~ 03-model.md
  + 05-controller.md
  + assets/mvc.svg

Moodle actions:
  UPDATE book
  UPDATE chapter "MVC"
  UPDATE chapter "Model"
  CREATE chapter "Controller"
  UPLOAD mvc.svg

Continue? [Y/n]
```

Para entornos no interactivos (futuro CI): flag `--yes` / `--non-interactive`.

### 17.2. No borrar silenciosamente

Si la nueva versión elimina un capítulo que existía en la desplegada:

```text
⚠ Este despliegue eliminará 1 capítulo del Book Moodle:
  - capitulo-observer

[Cancelar] [Confirmar despliegue]
```

Toda eliminación se registra en auditoría.

### 17.3. Idempotencia

Publicar v1.2.0 dos veces no crea dos Books ni duplica capítulos: los capítulos se identifican por su `id` estable, y el Book por `(courseid, source, content_id)` en la tabla.

---

## 18. Rollback

```bash
courseascode deploy --course 2026-2027 --book @dwes/ut03-mvc --version 1.1.0
```

- El rollback **reconstruye el Book desde Git**: es un redeploy de una versión conocida, no una restauración de copias de Moodle.
- Usa el mismo pipeline de §17 (plan + confirmación + ejecución idempotente).
- Las versiones RECALLED están bloqueadas para rollback salvo `--force` explícito.
- En la interfaz Moodle, el rollback es "desplegar una versión anterior" desde la página de versiones del Book.

---

## 19. Estados del despliegue

```text
NOT_DEPLOYED
UP_TO_DATE
UPDATE_AVAILABLE        (+ severity: normal | critical)
DRIFT_DETECTED          (el contenido en Moodle fue editado a mano)
DEPLOYING
ERROR
```

La severidad acompaña a `UPDATE_AVAILABLE` (badge amarillo vs. rojo en el plugin).

### 19.1. Detección de drift

Si un profesor edita el Book a mano desde Moodle, el siguiente chequeo compara el HTML actual con el `content_hash` registrado y muestra:

```text
⚠ Este Book fue modificado manualmente en Moodle.
  El próximo despliegue sobrescribirá esos cambios.
  [Ver diferencias] [Desplegar de todos modos] [Cancelar]
```

---

## 20. Validación

```bash
courseascode validate
```

Comprueba: YAML válido, IDs únicos, archivos existentes, capítulos existentes, referencias correctas, imágenes existentes, enlaces internos válidos, Markdown válido, estructura del Book, metadatos de catálogo presentes.

```text
$ courseascode validate

✓ course.yml
✓ books/ut03-mvc/book.yml
✓ 5 chapters
✓ 7 assets
✓ internal links
✓ Markdown
✓ catalog metadata

Validation successful.
```

Si hay errores:

```text
✗ 03-model.md
  Broken link: 07-ejemplo.md
```

- **No se puede publicar si falla la validación.**
- `validate` corre además como **status check bloqueante** en todo PR a `main` (§10.2).

---

## 21. Página de información de versión (plugin, solo profesores)

Cada Book gestionado tiene su página de versión en Moodle:

```text
Patrones MVC

Contenido:          @dwes/ut03-mvc
Versión publicada:  1.2.0
Git commit:         8f31a2c
Publicado:          12/10/2026 18:32
Curso:              DWES 2026-2027
Estado:             ● Sincronizado
```

Si hay versión más reciente:

```text
Versión publicada:          1.2.0
Última versión disponible:  1.3.0
Estado: ⚠ Hay una actualización disponible

[Ver cambios] [Actualizar]
```

Si es crítica (§11):

```text
⚠ ACTUALIZACIÓN CRÍTICA — 1.3.1 corrige un error grave de tu versión
[Ver corrección] [Actualizar a 1.3.1] [Actualizar en mis 3 cursos]
```

Si es una línea personal:

```text
Contenido:  @juan/ut03-mvc
Versión:    Basado en la oficial 1.2.0 · 3 cambios propios
Oficial:    1.3.0 disponible — tu rama va 2 commits por detrás
[Ver cambios oficiales]
```

**Privacidad:** esta página requiere capability de profesor. El alumnado nunca ve metadata Git (commits, ramas, mensajes). El HTML desplegado no incrusta ningún dato del repo.

---

## 22. Comparación de versiones

Mínimo en Beta: resumen estructural del diff entre la versión publicada y la candidata:

```text
v1.2.0 vs v1.3.0

+ Nuevo capítulo: Observer
~ Modificado: MVC
- Eliminado: Introducción histórica
~ 3 assets modificados
```

La arquitectura (`git diff` en el provider) debe permitir posteriormente un diff Markdown/HTML completo.

---

## 23. Paneles de administración

### 23.1. Panel del curso (plugin)

```text
Course as Code — DWES 2026-2027

Book              Published     Available    Estado
─────────────────────────────────────────────────────────
@dwes/ut03-mvc    v1.2.0        v1.2.0       ✓ UP TO DATE
@dwes/ut04-dao    v1.0.0        v1.1.0       ↑ UPDATE AVAILABLE
@dwes/ut05-api    v1.4.0        v1.4.1       ⚠ CRITICAL UPDATE
@juan/ut03-mvc    1.2.0+juan.3  —            ✓ Línea personal
```

Al seleccionar un Book: versiones disponibles, [Preview], [Compare], [Deploy], [Rollback a...].

### 23.2. Panel de gobernanza (post-beta)

```text
Pendiente de tu voto:

  ● UT03 · "Añade ejemplo de Observer en PHP 8.3"
    Autor: Juan · MINOR · hace 2 días · +85/-12 líneas
    [Ver cambios] [Ir a votar →]
```

Con recordatorios por mensajería Moodle si un PR supera N días sin quórum.

---

## 24. Auditoría

Cada despliegue registra: curso, book, source, versión, commit, moodle_book_id, usuario, timestamp, resultado, plan aplicado (incluidas eliminaciones confirmadas).

```text
2026-10-12 18:32 · DWES 2026-2027 · @dwes/ut03-mvc · v1.2.0 · 8f31a2c · success
```

La declaración de severidad/recall (§11) también se audita: quién, cuándo, motivo.

---

## 25. Autenticación y seguridad

- Cuenta técnica de Moodle con token y **capabilities mínimas**.
- Credenciales por variables de entorno; **nunca** en el repositorio:

```text
MOODLE_URL=
MOODLE_TOKEN=
CONTENT_REPO_URL=
CONTENT_REPO_KEY=
```

- HTML sanitizado en el renderer (§14.2).
- El servicio verifica la ACL de fuentes antes de desplegar desde una fuente privada.
- Comunicaciones servicio ↔ plugin por HTTPS con token.

---

## 26. Privacidad

1. **Repositorio privado por defecto.** El alumnado nunca accede a Git; consume únicamente vía Moodle.
2. **Limitación técnica documentada:** Git no admite permisos de *lectura* por rama. Quien clona el repo lee todas las ramas. Las ramas protegidas controlan escritura, no lectura. **No se promete privacidad de ramas dentro del repo compartido.**
3. **Ramas en el repo compartido = visibles al equipo.** La revisión colegiada lo exige: no se puede votar lo que no se puede leer.
4. **Privacidad real entre profesores = fork privado opt-in.** El profesor trabaja en su propio repo con el oficial como remote; cuando quiere aportar, abre PR desde el fork (el PR expone solo esos commits). La arquitectura lo soporta sin cambios: el fork es otra `source` con ACL propia.
5. **Material sensible prohibido** en el repo de contenidos: exámenes, soluciones, bancos de preguntas. Regla: si no podría aparecer en Moodle ante alumnos, no pertenece a este repo. Git retiene el historial y el pipeline asume contenido publicable.
6. **Metadata Git solo para profesores** (§21).

Matriz de visibilidad:

| Contenido | Visible para |
|---|---|
| `main` + tags oficiales | Consejo de profesores del curso |
| Ramas de propuesta (PRs) | Consejo |
| Ramas personales (repo compartido) | Equipo docente |
| Fork privado de un profesor | Solo él (+ servicio) |
| Books desplegados | Matriculados en cada curso |
| Páginas de versión / gobernanza | Solo profesores |

---

## 27. Integración con la plataforma Git

Requisitos de infraestructura (no features del sistema):

- Repo privado con `main` protegida (sin push directo).
- Required approvals = quórum por tipo de cambio (§10.2), `CODEOWNERS` por equipo.
- Status checks bloqueantes: `validate` + check de divergencia.
- Webhook de merge/PR → servicio (recálculo de estados y notificaciones).

No se implementa inicialmente CI/CD obligatorio de despliegue (§29). Una vez estable:

```text
GitHub/GitLab → CI/CD → courseascode deploy
```

---

## 28. Backup/restore y clonación de cursos

Caso frecuente: el curso "DWES 26/27" se crea **clonando** el de "25/26" (backup/restore o import de Moodle).

Comportamiento definido del plugin:

- Al restaurar un curso, las filas de `local_courseascode_deploy` se copian **re-asignadas al nuevo `courseid`** (nunca apuntan al curso origen).
- El curso clonado arranca vinculado a las mismas `(source, content_id, version)` que el origen — que es exactamente lo deseado: hereda los enlaces, y desde ahí el profesor actualiza cuando quiera.
- Los Books clonados se marcan para verificación de drift en el primer chequeo.

---

## 29. CLI

```text
courseascode validate                       # §20
courseascode preview <book>                 # §13
courseascode info <book>                    # metadata, capítulos, assets, commit
courseascode build <book>                   # render sin desplegar
courseascode deploy [--course C] [--book B] [--version V | --ref R] [--yes]
courseascode status [--course C]            # estados de despliegue
courseascode export --course C              # genera deployments/<curso>.yml (§9)
courseascode release mark <ref> --severity ... --fixed-in ... --reason ...
courseascode release list <book>
```

Ejemplo:

```text
$ courseascode info books/ut03-mvc

ID:          @dwes/ut03-mvc
Title:       MVC y patrones de diseño
Type:        book
Chapters:    5
Assets:      7
Git commit:  8f31a2c
Tags:        v1.0.0, v1.1.0, v1.2.0
```

---

## 30. Stack tecnológico

| Elemento | Elección |
|---|---|
| Lenguaje servicio | Python 3.12 |
| CLI | Typer |
| API + preview | FastAPI |
| Git | GitPython (interfaz `GitProvider` para futuros providers remotos) |
| Manifiestos | PyYAML + pydantic (esquemas) |
| Markdown | markdown-it-py (CommonMark; plugins: tablas, `container` para admonitions) |
| Resaltado | Pygments (`noclasses=True`) |
| Templates tema | Jinja2 |
| HTTP | httpx |
| Plugin | PHP según Moodle 4.x/5.x, `external_api`, Mustache, `install.xml` |
| Servicio | Docker; deploy keys de lectura por fuente |
| Dev Moodle | moodle-docker con el plugin en `local/courseascode` |

---

## 31. Fuera de alcance (Beta 0.2)

No se implementa (la arquitectura lo contempla):

- Quiz, GIFT, Assignment, Forum, Gradebook, SCORM, H5P.
- Editor WYSIWYG / editor Markdown integrado en web.
- Sistema de votación propio (se usa la plataforma Git).
- Panel de gobernanza "pendiente de tu voto" (post-beta).
- Actualización asistida de ramas personales (merge `main → rama` desde UI).
- Múltiples fuentes de catálogo con ACL (la tabla y el modelo lo soportan; la Beta opera con una fuente oficial).
- Plantillas de curso completo importables de un clic.
- Auto-actualización de hotfixes.
- GitHub Actions / GitLab CI de despliegue.
- Releases automáticas, sincronización bidireccional, edición Moodle → Git.
- Diff visual avanzado.

---

## 32. Criterios de aceptación

La Beta se considera terminada cuando pueda realizarse este flujo completo:

**Ciclo básico (autor):**

1. Crear `books/ut03-mvc/` con `book.yml` + 5 capítulos Markdown + assets.
2. `courseascode validate` → `Validation successful.`
3. `courseascode preview books/ut03-mvc` → Book con tema propio en el navegador.
4. Tag `book/ut03-mvc/v1.0.0`.

**Ciclo de importación (profesor desde cero):**

5. Un profesor entra a un curso Moodle vacío → Catálogo → ve `@dwes/ut03-mvc v1.0.0` con preview → **Añadir al curso** (sección elegida).
6. El sistema crea el Moodle Book con imágenes visibles y enlaces internos funcionando; la tabla registra `source`, `content_id`, `version`, `git_commit`.

**Ciclo de actualización:**

7. Modificar `02-mvc.md`, tag `v1.1.0`.
8. La interfaz Moodle muestra `UPDATE AVAILABLE` en ese curso.
9. El profesor ve el plan de cambios y publica v1.1.0.
10. El **mismo** Book Moodle se actualiza (sin duplicados).

**Ciclo de rollback:**

11. Desplegar de nuevo v1.0.0 → el Book vuelve exactamente a ese estado.

**Ciclo de gobernanza:**

12. Un PR a `main` sin `validate` en verde no puede mergearse; un PR MINOR requiere 2 aprobaciones.

**Ciclo de hotfix:**

13. Se marca v1.1.0 como `critical` con fix en v1.1.1 → los cursos afectados ven el aviso crítico; nuevos despliegues de la versión retirada quedan bloqueados.

---

## 33. Resultado esperado

```text
                 GIT (repo privado)
                  │
        ┌─────────┴─────────┐
        │                   │
     v1.0.0              v1.1.0          main protegida + PR con quórum
        │                   │
        └─────────┬─────────┘
                  │
             Catálogo / Deploy
                  │
                  ▼
               Moodle
                  │
        ┌─────────┴──────────┐
        │                    │
   DWES 25/26           DWES 26/27
     v1.0.0                v1.1.0
```

Y preparado para evolucionar:

```text
                    Course as Code
                          │
             ┌────────────┼────────────┐
             │            │            │
           Books        Pages        Quizzes
             │            │            │
             └────────────┼────────────┘
                          │
                       Moodle
```

**Prioridad absoluta de la Beta:** demostrar sólido el ciclo

```text
Markdown → Git → versión → catálogo → importar → Moodle Book
→ identificación de versión → actualización → hotfix → rollback
```

No añadir funcionalidades adicionales hasta que ese ciclo sea sólido.

---

## 34. Roadmap post-Beta (orientativo)

1. Editor Markdown integrado (edición desde Moodle/web).
2. Actualización asistida de ramas personales con diff visual.
3. Panel de gobernanza + recordatorios de voto.
4. Plantillas de curso importables.
5. Multi-fuente de catálogo con ACL completa.
6. CI/CD de despliegue.
7. Pages, Quizzes (con su propio modelo de privacidad para bancos de preguntas), Assignments.

---

## 35. Glosario

- **Book**: recurso Moodle de tipo libro; unidad de contenido de la Beta.
- **Source**: origen del contenido (rama del repo oficial o fork privado).
- **Release**: versión de contenido publicada mediante tag Git.
- **Deployment**: asignación de una versión concreta a un curso Moodle concreto.
- **Binding**: registro curso↔versión en la tabla del plugin.
- **Consejo de curadores**: profesores de la asignatura con derecho de voto sobre `main`.
- **Drift**: modificación manual del Book en Moodle fuera del sistema.
- **Recall**: retirada administrativa de una versión (bloquea nuevos despliegues, no altera los existentes).
