Aquí tienes el contenido completo del documento para copiar a tu proyecto:

---

```markdown
# Especificación técnica: plugin Moodle `mod_liamd`
## LiaScript Markdown Delivery — Edición integrada desde Moodle con proxy de contenido

**Versión**: 0.1.0-draft  
**Fecha**: 2026-11-12  
**Estado**: Listo para desarrollo  
**Autor**: Especificación generada para agente de desarrollo  

---

## 1. Resumen ejecutivo

Plugin de Moodle que permite al profesorado:
1. Explorar un repositorio Git de materiales didácticos en formato LiaScript Markdown
2. Seleccionar un fichero y crear una rama de edición personal (o editar `main` si tiene permisos)
3. Abrir el fichero directamente en LiaScript LiveEditor (instancia pública inicialmente, self-hosted en fase 2) con el contenido servido por un endpoint del propio plugin (Patrón B: proxy de contenido)
4. Guardar los cambios desde el LiveEditor de vuelta al repositorio Git mediante commit automático
5. Generar automáticamente tres artefactos accesibles por cada recurso: SCORM 2004 (interactivo), ePub (accesibilidad visual), PDF (impresión/baja visión parcial)

El repositorio Git es la **única fuente de verdad**. Moodle nunca almacena el contenido fuente, solo metadatos de vinculación y artefactos generados.

---

## 2. Arquitectura general

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           MOODLE (servidor)                             │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                    PLUGIN mod_liamd                              │   │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐  │   │
│  │  │ Explorador  │  │  content.php│  │      save.php           │  │   │
│  │  │   de repo   │  │  (proxy md) │  │   (commit endpoint)     │  │   │
│  │  └─────────────┘  └─────────────┘  └─────────────────────────┘  │   │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐  │   │
│  │  │  Git Client │  │ Task Queue  │  │   Artifact Manager      │  │   │
│  │  │  (API Git)  │  │  (adhoc)    │  │   (SCORM/ePub/PDF)      │  │   │
│  │  └─────────────┘  └─────────────┘  └─────────────────────────┘  │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                              │                                          │
│  ┌───────────────────────────┼─────────────────────────────────────┐   │
│  │      BASE DE DATOS        │      SISTEMA DE FICHEROS            │   │
│  │  {prefix}_liamd           │      $CFG->dataroot/liamd/          │   │
│  │  {prefix}_liamd_artefact  │      └── <cmid>/                    │   │
│  │                           │          ├── scorm2004.zip          │   │
│  │                           │          ├── accessible.epub        │   │
│  │                           │          └── printable.pdf          │   │
│  └───────────────────────────┘                                     │   │
└──────────────────────────────┼─────────────────────────────────────┘   │
                               │                                          │
┌──────────────────────────────┼─────────────────────────────────────┐   │
│                         GIT (GitHub/GitLab)                        │   │
│  Repo de materiales: organización/unidad-formativa                 │   │
│  Ramas: main, edicion/<usuario>/<archivo>, plantillas/*            │   │
└────────────────────────────────────────────────────────────────────┘   │
                               ▲                                          │
                               │ HTTPS API + token de servidor           │
┌──────────────────────────────┴─────────────────────────────────────┐   │
│                    LIVEEDITOR LIASCRIPT                            │   │
│  Fase 1: https://liascript.github.io/LiveEditor/                   │   │
│  Fase 2: https://liascript-editor.midominio.com (self-hosted)      │   │
│                                                                    │   │
│  Carga contenido vía ?url=<endpoint content.php>                   │   │
│  Guarda vía POST a <endpoint save.php>                             │   │
└────────────────────────────────────────────────────────────────────┘   │
                               ▲                                          │
                               │ Navegador del profesor                  │
                               │ (autenticado en Moodle)                 │
```

---

## 3. Decisiones de arquitectura (ya tomadas, no reabrir)

| Decisión | Elección | Justificación |
|----------|----------|---------------|
| Patrón de servicio de contenido | **B: Proxy de contenido** (`content.php`) | Repo puede ser privado; inyección de metadatos; control de CORS |
| Editor | **LiveEditor externo** (fase 1: pública; fase 2: self-hosted) | No reinventar editor; preview real LiaScript; migración transparente |
| Guardado | **POST de vuelta al plugin** (`save.php`) | Commit automático sin OAuth de GitHub; mensajes estandarizados |
| Rama por defecto | `edicion/<username>/<archivo>` | Aislamiento de cambios; `main` protegido solo para mantenedores |
| Detección de conflictos | SHA en URL + verificación en save | Optimistic locking; último escritor no gana silenciosamente |
| Generación de artefactos | Adhoc task de Moodle tras commit | No bloquear UI; reintentos; trazabilidad |
| Formatos de salida | SCORM 2004 + ePub + PDF | Accesibilidad (visual/auditiva) + interacción + impresión |
| Fuente de verdad | **Git** (Moodle solo metadatos) | Versionado nativo; diffs; rollback |

---

## 4. Requisitos funcionales

### RF-01: Explorador de repositorio

**Actor**: Profesor con capacidad `mod/liamd:viewrepo`

**Flujo**:
1. Al crear instancia de actividad `mod_liamd`, el profesor selecciona modo "Importar desde repositorio"
2. El plugin muestra árbol de archivos `.md` del repo (vía API Git, caché 5 min)
3. Cada nodo muestra: nombre, rama actual, último commit (autor, fecha, mensaje), tamaño
4. Acciones por archivo:
   - **Vista previa**: abre `view.php` con iframe a LiveEditor en modo solo-lectura
   - **Editar**: flujo RF-02
   - **Usar en curso**: vincula el archivo a la actividad sin editar (solo lectura desde repo)

**Restricciones**:
- Solo archivos `.md` y `.liascript` listados
- Máximo 100 archivos por nivel (paginación)
- No se muestran archivos en `.gitignore` del repo

### RF-02: Creación de rama de edición

**Actor**: Profesor con capacidad `mod/liamd:edit`

**Flujo**:
1. Profesor selecciona "Editar" sobre archivo `unidad-3.md` en rama `main`
2. Plugin verifica si existe rama `edicion/<username>/unidad-3`
3. **Si no existe**:
   - Muestra diálogo: "Se creará tu espacio de edición personal: `edicion/<username>/unidad-3`"
   - Opciones: [Crear y editar] [Cancelar]
   - Al crear: API Git crea rama desde último commit de `main`
4. **Si existe**:
   - Muestra: último commit de la rama, diff resumen vs `main` (líneas +/-), fecha última edición
   - Opciones: [Continuar editando] [Ver diff completo] [Resetear a main] [Editar main directamente]*

*Opción "Editar main" solo visible si profesor tiene capacidad `mod/liamd:editmain`

**Reglas de negocio**:
- Una rama de edición por usuario por archivo (no múltiples)
- El nombre de rama se sanitiza: lowercase, sin espacios, máx 100 chars
- Si el archivo se renombra en `main`, la rama de edición se marca como "stale" (aviso, no bloqueo)

### RF-03: Apertura en LiveEditor

**Actor**: Profesor en flujo de edición

**Flujo técnico**:
1. Plugin construye URL del LiveEditor:
   ```
   https://liascript.github.io/LiveEditor/
     ?url=<moodle_baseurl>/mod/liamd/content.php
       %3Fcmid%3D123
       %26file%3Dunidades%2Funidad-3.md
       %26branch%3Dedicion%2Fprofesor-x%2Funidad-3
       %26sha%3Db2e4f6a123...
     &mode=edit
   ```
2. Redirige en nueva pestaña (`target=_blank`, `rel="noopener noreferrer"`)
3. LiveEditor hace GET a `content.php` con los parámetros
4. `content.php` responde con el contenido Markdown + metadatos inyectados (ver sección 6.2)
5. LiveEditor renderiza editor + preview

**Requisitos de `content.php`**:
- Autenticación: sesión Moodle activa (o token de un solo uso si se requiere)
- CORS: `Access-Control-Allow-Origin: https://liascript.github.io` (configurable en settings)
- Rate limiting: 60 req/min por usuario
- Cache: `Cache-Control: no-cache, must-revalidate` (siempre contenido fresco)

### RF-04: Guardado desde LiveEditor

**Actor**: Profesor editando en LiveEditor

**Flujo técnico**:
1. LiveEditor (modificado o vía userscript) detecta que la URL de carga es del plugin Moodle
2. Sustituye el botón "Save to GitHub" por "Guardar en Moodle" (o añade botón adicional)
3. Al pulsar, hace POST a `save.php` con:
   ```json
   {
     "cmid": 123,
     "file": "unidades/unidad-3.md",
     "branch": "edicion/profesor-x/unidad-3",
     "original_sha": "b2e4f6a123...",
     "content": "---\ntitle: ...\n---\n# Unidad 3\n...",
     "commit_message": "Editado desde Moodle"
   }
   ```
4. `save.php` procesa (ver sección 6.3)
5. Respuesta JSON indica éxito, conflicto, o error

**Casos de respuesta**:
- `200 OK`: `{"status": "ok", "new_sha": "...", "artifacts_queued": true}`
- `409 Conflict`: `{"status": "conflict", "resolution_branch": "resolucion/profesor-x/unidad-3", "diff_url": "..."}`
- `403 Forbidden`: `{"status": "error", "message": "No tienes permiso para editar esta rama"}`

### RF-05: Generación de artefactos

**Trigger**: Commit exitoso en `save.php` (o manual desde interfaz de administración)

**Proceso** (adhoc task `\mod_liamd\task\generate_artifacts`):
1. Recibe: `cmid`, `file`, `branch`, `new_sha`
2. Lanza contenedor Docker `liascript/exporter` con:
   ```
   docker run --rm \
     -v /tmp/liamd-<cmid>:/output \
     liascript/exporter \
     --git-url <repo_url> \
     --git-branch <branch> \
     --git-file <file> \
     --format scorm2004 --scorm-embed --scorm-masteryScore 80 \
     --output /output/scorm2004.zip
   ```
3. Repite para `--format epub` y `--format pdf`
4. Mueve artefactos a `$CFG->dataroot/liamd/<cmid>/`
5. Registra en `{prefix}_liamd_artifact` con timestamp y SHA
6. Notifica al profesor (mensaje Moodle) cuando completado

**Requisitos**:
- Timeout: 300 segundos por formato
- Reintentos: 3 con backoff exponencial
- Si falla un formato, los demás continúan; se registra error parcial
- No bloquear la respuesta al profesor (fire and forget desde save.php)

### RF-06: Visualización del recurso en el curso

**Actor**: Estudiante (o profesor en vista previa)

**Flujo**:
1. Al entrar a la actividad `mod_liamd`, se muestra:
   - **Por defecto**: iframe embebido con el SCORM 2004 (vía `mod_scorm` interno del plugin, o redirección a `mod_scorm` estándar)
   - **Alternativas accesibles**: enlaces descargables a ePub y PDF
2. El estudiante elige su formato preferido
3. El seguimiento del SCORM (notas, progreso) se guarda en el gradebook de Moodle

**Nota de accesibilidad**: Los enlaces a ePub/PDF deben tener atributos `aria-label` descriptivos:
```html
<a href="..." aria-label="Descargar Unidad 3 en formato ePub (compatible con lectores de pantalla)">
```

---

## 5. Requisitos no funcionales

### RNF-01: Seguridad

- **Token de Git**: almacenado en `config_plugins` tabla, nunca en código ni en cliente
- **CORS**: `content.php` solo acepta origen del LiveEditor configurado en settings
- **Autorización**: todas las operaciones verifican `sesskey` de Moodle + capacidades del contexto del curso
- **Sanitización**: nombres de archivo validados contra path traversal (`..`, `/etc/`, etc.)
- **Secrets**: nunca en URLs (usar POST body o headers para datos sensibles)

### RNF-02: Rendimiento

- **Caché de explorador**: árbol de repo cacheado 5 min en `MUC` (Moodle Universal Cache)
- **Caché de contenido**: contenido de archivos cacheado por SHA (inmutable, cache largo)
- **Generación async**: nunca bloquear request HTTP con liaex (puede tardar 60-120s)
- **Límites**: archivos Markdown máx 1 MB; ramas de edición máx 50 por usuario

### RNF-03: Disponibilidad

- **Degradación graceful**: si Git no responde, mostrar último contenido cacheado con aviso
- **Reintentos**: API Git con exponential backoff (1s, 2s, 4s)
- **Monitoreo**: log de todos los commits y generaciones de artefactos (`{prefix}_liamd_log`)

### RNF-04: Accesibilidad (WCAG 2.1 AA)

- Toda la UI del plugin (explorador, formularios) debe ser navegable por teclado
- Contraste mínimo 4.5:1 en todos los textos
- Los iframes del SCORM deben tener `title` descriptivo
- Los enlaces a artefactos deben indicar formato y tamaño del fichero

---

## 6. Diseño de endpoints

### 6.1 `view.php` — Vista principal de la actividad

**Parámetros**: `id` (cmid)

**Comportamiento**:
- Si el usuario tiene capacidad `mod/liamd:edit`: muestra barra de herramientas con [Editar en LiveEditor] [Regenerar artefactos] [Ver historial]
- Si es estudiante: muestra el SCORM embebido + enlaces a alternativas

### 6.2 `content.php` — Proxy de contenido (Patrón B)

**Método**: GET  
**Autenticación**: Sesión Moodle (cookie) o token de un solo uso  
**Parámetros**:
| Parámetro | Tipo | Requerido | Descripción |
|-----------|------|-----------|-------------|
| `cmid` | int | sí | ID del course module |
| `file` | path | sí | Ruta del archivo en el repo |
| `branch` | string | sí | Rama (ej: `edicion/user/file` o `main`) |
| `sha` | string | no | SHA esperado (para validación) |
| `readonly` | bool | no | Si es true, no inyecta metadatos de guardado |

**Respuesta exitosa (200)**:
```
Content-Type: text/plain; charset=utf-8
Access-Control-Allow-Origin: https://liascript.github.io
X-LiaMD-Branch: edicion/profesor-x/unidad-3
X-LiaMD-SHA: b2e4f6a123...
X-LiaMD-Readonly: false

---
title: Unidad 3
liascript-moodle:
  cmid: 123
  file: unidades/unidad-3.md
  branch: edicion/profesor-x/unidad-3
  sha: b2e4f6a123...
  save_endpoint: https://moodle.com/mod/liamd/save.php
  readonly: false
---

# Contenido original del archivo...
```

**Inyección de metadatos**: El bloque `liascript-moodle` se añade al YAML front matter existente (o se crea si no hay). Si ya existe, se sobrescribe.

**Errores**:
- `403`: Usuario no autenticado o sin permisos
- `404`: Archivo no encontrado en la rama
- `409`: SHA no coincide (el archivo cambió desde que se generó la URL)
- `500`: Error de API Git

### 6.3 `save.php` — Endpoint de guardado

**Método**: POST  
**Content-Type**: `application/json`  
**Autenticación**: Sesión Moodle + `sesskey` en header `X-Moodle-Sesskey`

**Body**:
```json
{
  "cmid": 123,
  "file": "unidades/unidad-3.md",
  "branch": "edicion/profesor-x/unidad-3",
  "original_sha": "b2e4f6a123...",
  "content": "...(Markdown completo)...",
  "commit_message": "Editado desde Moodle por profesor-x"
}
```

**Lógica de negocio**:
1. Validar sesión, capacidad `mod/liamd:edit`, y que `cmid` corresponde a una instancia `mod_liamd`
2. Verificar que `branch` es `edicion/<username>/...` o `main` (si tiene `mod/liamd:editmain`)
3. Obtener SHA actual del archivo en Git
4. **Si `current_sha !== original_sha`**: conflicto
   - Crear rama `resolucion/<username>/<timestamp>-<archivo>` desde `current_sha`
   - Commit del contenido en esa rama
   - Responder 409 con datos de la rama de resolución
5. **Si coincide**: commit normal en `branch`
6. Actualizar registro en `{prefix}_liamd` con nuevo SHA
7. Encolar adhoc task `generate_artifacts`
8. Responder 200 con nuevo SHA

**Respuesta éxito (200)**:
```json
{
  "status": "ok",
  "new_sha": "c3d5e7f456...",
  "branch": "edicion/profesor-x/unidad-3",
  "artifacts_queued": true,
  "message": "Cambios guardados. Generando SCORM, ePub y PDF..."
}
```

**Respuesta conflicto (409)**:
```json
{
  "status": "conflict",
  "message": "El archivo fue modificado por otro usuario mientras editabas.",
  "resolution_branch": "resolucion/profesor-x/20261112-153045-unidad-3",
  "diff_url": "https://github.com/org/repo/compare/edicion/profesor-x/unidad-3...resolucion/profesor-x/20261112-153045-unidad-3",
  "options": [
    "Abrir editor de resolución de conflictos",
    "Descartar mis cambios y recargar versión actual",
    "Forzar guardado (sobrescribir)"
  ]
}
```

### 6.4 `edit.php` — Orquestador de apertura en LiveEditor

**Método**: GET  
**Parámetros**: `cmid`, `file`, `branch` (opcional, default: crear/sugerir rama de edición)

**Flujo**:
1. Si no se especifica `branch`: verificar si existe `edicion/<username>/<file>`; si existe, usarla; si no, mostrar diálogo de creación
2. Obtener SHA actual del archivo
3. Construir URL del LiveEditor (configurable en settings: pública o self-hosted)
4. Redirigir con `302 Found` a la URL construida

**URL construida (fase 1)**:
```
https://liascript.github.io/LiveEditor/?url=<urlencode(content.php?cmid=...&file=...&branch=...&sha=...)>
```

**URL construida (fase 2, self-hosted)**:
```
https://liascript-editor.midominio.com/?url=<...>&api_save=<urlencode(save.php)>
```

### 6.5 `webhook.php` — Webhook de Git (opcional, para repos en GitHub/GitLab)

**Método**: POST  
**Autenticación**: HMAC secret (configurable)

**Uso**: Si el repo recibe commits externos (fuera del plugin), actualizar caché y regenerar artefactos si afecta a ramas vinculadas.

---

## 7. Esquema de base de datos

### Tabla `{prefix}_liamd` (instancias de actividad)

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `id` | bigint(10) PK | ID estándar Moodle |
| `course` | bigint(10) | Curso al que pertenece |
| `name` | varchar(255) | Nombre de la actividad |
| `intro` | text | Descripción |
| `introformat` | smallint(4) | Formato de intro |
| `repo_url` | varchar(255) | URL del repo Git |
| `repo_branch` | varchar(100) | Rama principal (default: `main`) |
| `file_path` | varchar(255) | Ruta del archivo .md en el repo |
| `edit_branch` | varchar(100) | Rama de edición activa (null si solo lectura) |
| `current_sha` | char(40) | SHA del último commit conocido |
| `timecreated` | bigint(10) | Timestamp creación |
| `timemodified` | bigint(10) | Timestamp última modificación |

### Tabla `{prefix}_liamd_artifact` (artefactos generados)

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `id` | bigint(10) PK | ID artefacto |
| `liamd_id` | bigint(10) FK | Referencia a instancia |
| `type` | varchar(20) | `scorm2004`, `epub`, `pdf` |
| `file_path` | varchar(255) | Ruta en dataroot |
| `file_size` | bigint(10) | Bytes |
| `source_sha` | char(40) | SHA del commit que generó este artefacto |
| `status` | varchar(20) | `pending`, `ready`, `failed` |
| `timecreated` | bigint(10) | Timestamp generación |
| `error_message` | text | Si status = failed |

### Tabla `{prefix}_liamd_edit` (sesiones de edición)

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `id` | bigint(10) PK | ID sesión |
| `liamd_id` | bigint(10) FK | Instancia |
| `user_id` | bigint(10) | Usuario que edita |
| `branch` | varchar(100) | Rama de edición |
| `opened_at` | bigint(10) | Timestamp apertura editor |
| `last_save` | bigint(10) | Timestamp último guardado |
| `closed_at` | bigint(10) | Timestamp cierre (null si activa) |

---

## 8. Capacidades y permisos

| Capacidad | Rol por defecto | Descripción |
|-----------|-----------------|-------------|
| `mod/liamd:view` | estudiante, profesor, manager | Ver la actividad y artefactos |
| `mod/liamd:viewrepo` | profesor, manager | Explorar el repositorio Git |
| `mod/liamd:edit` | profesor, manager | Crear ramas de edición y guardar cambios |
| `mod/liamd:editmain` | manager | Editar rama `main` directamente |
| `mod/liamd:manageartifacts` | manager | Regenerar artefactos manualmente, borrar artefactos |
| `mod/liamd:viewlogs` | manager | Ver historial de commits y generaciones |

---

## 9. Configuración del plugin (settings)

Sección: **Administración del sitio → Plugins → Actividades → LiaScript Markdown**

| Setting | Tipo | Default | Descripción |
|---------|------|---------|-------------|
| `liamd_git_provider` | select | `github` | `github`, `gitlab`, `gitea`, `custom` |
| `liamd_git_api_url` | text | `https://api.github.com` | URL base de la API |
| `liamd_git_token` | password | — | Token de acceso (con scope `repo` o `read/write` mínimo) |
| `liamd_git_org` | text | — | Organización/propietario del repo de materiales |
| `liamd_git_repo` | text | — | Nombre del repositorio |
| `liamd_liveeditor_url` | text | `https://liascript.github.io/LiveEditor/` | URL base del LiveEditor |
| `liamd_liveeditor_selfhosted` | checkbox | false | Marcar cuando se despliegue instancia propia |
| `liamd_cors_origin` | text | `https://liascript.github.io` | Origen permitido en content.php |
| `liamd_artifacts_enabled` | checkbox | true | Generar SCORM/ePub/PDF automáticamente |
| `liamd_artifacts_scorm_mastery` | int | 80 | Nota mínima de aprobado en SCORM (%) |
| `liamd_max_file_size` | int | 1048576 | Tamaño máximo de .md en bytes |
| `liamd_webhook_secret` | password | — | Secreto para verificar webhooks de Git |

---

## 10. Integración con LiveEditor (detalle técnico)

### Fase 1: LiveEditor público (sin modificar)

El LiveEditor oficial no soporta guardado personalizado. Soluciones:

**Opción A: Userscript/Greasemonkey** (recomendada para prototipo)
- Script que detecta `?url=.*content.php` en la URL
- Añade botón "Guardar en Moodle" que hace fetch a `save.php`
- Inyecta los metadatos del YAML `liascript-moodle` en la UI

**Opción B: Fork del LiveEditor** (recomendada para producción)
- Clonar [LiaScript/LiveEditor](https://github.com/LiaScript/LiveEditor)
- Modificar el componente de toolbar para detectar `save_endpoint` en el front matter
- Compilar y servir en `https://liascript-editor.midominio.com`
- Ventaja: integración nativa, sin hacks de navegador

### Fase 2: LiveEditor self-hosted

Requisitos de despliegue:
- Node.js 18+ (build estático)
- Servir con Caddy/Nginx (HTTPS obligatorio para Service Workers)
- Configurar `save_endpoint` por defecto al Moodle institucional

### Contrato de comunicación LiveEditor ↔ Plugin

El LiveEditor debe leer del front matter:
```yaml
liascript-moodle:
  save_endpoint: "https://moodle.com/mod/liamd/save.php"
  readonly: false
```

Y hacer POST a ese endpoint con el contenido actual del editor.

---

## 11. Generación de artefactos (detalle técnico)

### Contenedor liaex

Imagen: `liascript/exporter:latest` (o versión fijada en settings)

Comando SCORM 2004:
```bash
docker run --rm \
  --network none \
  -v /tmp/liamd-<cmid>-<sha>:/output \
  liascript/exporter \
  --git-url "https://<token>@github.com/org/repo.git" \
  --git-branch "edicion/profesor-x/unidad-3" \
  --git-file "unidades/unidad-3.md" \
  --format scorm2004 \
  --scorm-embed \
  --scorm-masteryScore 80 \
  --output "/output/scorm2004.zip"
```

Comando ePub:
```bash
docker run --rm \
  --network none \
  -v /tmp/liamd-<cmid>-<sha>:/output \
  liascript/exporter \
  --git-url "..." --git-branch "..." --git-file "..." \
  --format epub \
  --epub-title "Unidad 3" \
  --epub-language "es" \
  --output "/output/accessible.epub"
```

Comando PDF:
```bash
docker run --rm \
  --shm-size=1g \
  -v /tmp/liamd-<cmid>-<sha>:/output \
  liascript/exporter \
  --git-url "..." --git-branch "..." --git-file "..." \
  --format pdf \
  --output "/output/printable.pdf"
```

**Nota**: PDF usa Puppeteer/Chromium → requiere `--shm-size` y más memoria. Ejecutar en cola separada con más recursos.

### Almacenamiento de artefactos

```
$CFG->dataroot/liamd/
├── 123/                          # cmid = 123
│   ├── scorm2004.zip            # último SCORM generado
│   ├── accessible.epub
│   ├── printable.pdf
│   └── history/                  # versiones anteriores (opcional, rotación 5)
│       ├── 20261110-a3f2c1d/
│       └── 20261112-b2e4f6a/
```

---

## 12. Flujos de usuario (diagramas de secuencia)

### Flujo principal: Profesor edita material existente

```
Profesor          Moodle(mod_liamd)      Git API           LiveEditor
   │                    │                  │                  │
   │─[1] Explorar repo──▶│                  │                  │
   │◀──[2] Lista .md─────│                  │                  │
   │                    │                  │                  │
   │─[3] "Editar"───────▶│                  │                  │
   │◀──[4] Diálogo rama──│                  │                  │
   │─[5] "Crear rama"───▶│─[6] Create branch▶│                  │
   │                    │◀──[7] Branch creada                 │
   │◀──[8] 302 Redirect─│                  │                  │
   │─────────────────────────────────────────────────────────▶│
   │                    │                  │◀─[9] GET content──│
   │                    │◀─[10] GET file───│                  │
   │                    │─[11] md+meta────▶│                  │
   │                    │                  │                  │
   │                    │                  │◀─[12] Edita───────│
   │                    │                  │◀─[13] POST save───│
   │                    │◀─[14] Commit─────│                  │
   │                    │─[15] Commit──────▶│                  │
   │                    │◀─[16] New SHA─────│                  │
   │                    │─[17] 200 OK──────▶│                  │
   │                    │                  │                  │
   │                    │─[18] Queue task──▶│                  │
   │                    │   (liaex async)   │                  │
```

### Flujo de conflicto

```
Profesor          Moodle(mod_liamd)      Git API
   │                    │                  │
   │─[1] POST save──────▶│                  │
   │   (sha: abc123)     │                  │
   │                    │─[2] GET sha──────▶│
   │                    │◀──[3] sha: def456─│
   │                    │   (¡diferente!)   │
   │                    │                  │
   │                    │─[4] Create branch─▶
   │                    │   resolucion/...  │
   │                    │─[5] Commit────────▶
   │                    │                  │
   │◀──[6] 409 Conflict──│                  │
   │   + rama resolución │                  │
```

---

## 13. Manejo de errores y edge cases

| Escenario | Comportamiento |
|-----------|----------------|
| Git API caída | Mostrar último contenido cacheado con banner "Modo offline" |
| Archivo > 1 MB | Rechazar con mensaje "Archivo demasiado grande para edición online" |
| Rama de edición tiene conflictos con main | Permitir edición, pero avisar al abrir: "Esta rama tiene divergencias con main" |
| Profesor cierra editor sin guardar | Sesión `liamd_edit` queda `closed_at = null` > 24h → limpiar con cron |
| Generación de artefactos falla | Notificar al profesor, mantener artefactos anteriores si existen |
| Estudiante accede durante regeneración | Servir artefactos anteriores (si existen) o mensaje "Contenido actualizándose" |
| Token de Git expira | Log error, notificar a admin, modo solo-lectura |

---

## 14. Cron y tareas programadas

| Tarea | Frecuencia | Descripción |
|-------|------------|-------------|
| `liamd_cleanup_sessions` | Diaria | Cerrar sesiones de edición abandonadas |
| `liamd_sync_repo` | Cada 5 min | Actualizar caché de árbol de repo (si no hay webhook) |
| `liamd_retry_artifacts` | Cada 15 min | Reintentar generaciones fallidas |
| `liamd_rotate_history` | Semanal | Rotar historial de artefactos (mantener últimas 5 versiones) |

---

## 15. Checklist de desarrollo

### Fase 1: MVP (4-6 semanas)

- [ ] Estructura base del plugin (boilerplate Moodle)
- [ ] Tablas de BD (install.xml)
- [ ] `content.php` con autenticación y CORS
- [ ] `save.php` con lógica de conflicto básica
- [ ] Explorador de repo (RF-01) en `view.php`
- [ ] Creación de ramas (RF-02)
- [ ] Integración con LiveEditor público vía userscript (RF-03, RF-04)
- [ ] Generación SCORM con liaex (RF-05, solo SCORM)
- [ ] Visualización básica para estudiante (RF-06)

### Fase 2: Accesibilidad completa (2-3 semanas)

- [ ] Generación ePub y PDF
- [ ] Enlaces de descarga accesibles con aria-labels
- [ ] Validación WCAG 2.1 AA de la UI del plugin
- [ ] Testing con NVDA/VoiceOver

### Fase 3: Producción (2-4 semanas)

- [ ] LiveEditor self-hosted
- [ ] Webhooks de Git para sync en tiempo real
- [ ] Sistema de logs y monitoreo
- [ ] Documentación de usuario (profesorado)
- [ ] Pruebas de carga (100 profesores simultáneos)

---

## 16. Dependencias externas

| Dependencia | Versión | Uso |
|-------------|---------|-----|
| Moodle | 4.1+ | Plataforma base |
| PHP | 8.0+ | Runtime |
| Docker | 20.10+ | Contenedor liaex |
| `liascript/exporter` | latest | Generación de artefactos |
| Node.js | 18+ | Solo para build de LiveEditor self-hosted |

---

## 17. Referencias

- LiaScript LiveEditor: https://liascript.github.io/LiveEditor/
- LiaScript Exporter: https://github.com/LiaScript/exporter
- LiaScript Docs: https://liascript.github.io/
- Moodle Plugin Development: https://moodledev.io/
- SCORM 2004 Runtime: https://scorm.com/scorm-explained/technical-scorm/run-time/run-time-reference/

---

**Fin del documento**
```

---

Copia este bloque completo en un fichero `mod_liamd_spec.md` en tu proyecto. ¿Necesitas que ajuste alguna sección antes de que lo lleves al agente de desarrollo?