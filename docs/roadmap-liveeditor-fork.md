# Roadmap — Fork FPVirtual/LiveEditor (LiaEdit)

**Versión**: 0.1.0-draft
**Fecha**: 2026-11-13
**Estado**: Aprobado para desarrollo — pendiente de desglose en tareas
**Documentos base**:

- `docs/desarrollo-liaeditor-moodle-v1.md` (decisiones D1–D10, fases)
- `docs/cambio-curso-a-liascript.md` (especificación `mod_liamd` v0.1.0)

**Repositorio**: <https://github.com/FPVirtual/LiveEditor>
(fork de <https://github.com/LiaScript/LiveEditor>, HEAD actual
`10c845b "Version bump to 2.2.0"`, sin cambios propios todavía)

---

## 1. Propósito

Este documento define **qué cambios se hacen sobre el fork de LiaEdit y
cómo se aborda cada uno**, para que el editor encaje en la arquitectura
LiaEditor–Moodle v1:

- El profesor edita markdown LiaScript alojado en Git **sin cuenta
  propia** (D1): el guardado va contra `save.php` del plugin Moodle,
  con token de un solo uso (D9).
- El parche es **mínimo, genérico y aislado** (D10): "si el documento
  declara un endpoint de guardado, el editor muestra Guardar/Publicar
  contra ese endpoint" — válido para cualquier LMS y candidato a
  contribuir upstream.

Fuera de alcance: la colaboración WebRTC/WebSocket (cuestión abierta #6
del documento de arquitectura) y el exporter server-side (`liaex`, que
vive en el engine, no en el fork).

---

## 2. Estado actual del fork (verificado leyendo el código)

Hechos relevantes del código upstream que condicionan los cambios:

- **App Vue 3 + Parcel 2**, PWA, build estático → `dist/`.
  Enrutado propio **por query string** (`src/index.ts:81-127`):
  `?/edit/:storageId`, `?/show/file/:fileUrl`, `?/embed/...`.
- **Dos flujos de apertura distintos**:
  - `?/show/file/:fileUrl` (`src/views/File.vue`): hace `fetch` de la
    URL, reescribe enlaces relativos (`replaceURLs`) y renderiza con
    `LiaScript.vue :content`, **sin proyecto ni guardado**.
  - `?/edit/:storageId` (`src/views/Edit.vue` → `LiaScript.vue`):
    proyecto completo en IndexedDB (Dexie, `src/ts/indexDB.ts`) con
    documento Yjs (`src/ts/ProjectDoc.ts`).
- **Crear proyectos ya está resuelto**:
  `createProjectFromFiles(files, meta)` (`src/ts/createProject.ts:57`)
  importa ficheros al Y.Doc, persiste meta en Dexie y navega al editor.
  Es el punto de entrada natural para "abrir desde URL".
- **La meta del proyecto** vive en Dexie (`data` store, clave = id),
  se observa con `watch()` y llega a `LiaScript.vue` como `this.meta`.
  Ya guarda vínculos externos (`meta.github`, `meta.gitlab`,
  `meta.localFolder`): nuestro `meta.lms` sigue ese patrón.
- **Toolbar central en `src/views/LiaScript.vue`** (navbar, líneas
  ~978-1184): izquierda = curso, centro = modos de vista + compilar,
  derecha = conexión/ayuda/idioma/compartir. Ahí van los botones nuevos.
- **El contenido editable** se lee con
  `this.$refs.editor.getMainValue()` (Y.Text principal) y el activo
  mostrado con `getPreviewValue()` (`src/components/Editor.vue:266-309`).
- **Integraciones GitHub/GitLab** (Gist OAuth, push/pull/publish) se
  construyen en `shareGroups` de `LiaScript.vue:317-426` y usan
  `process.env.GITHUB_CLIENT_ID` (`src/ts/Gist.ts:39`). Sin `.env`
  fallan con OAuth; **no forman parte de nuestro flujo (D1)** y se
  ocultan (cambio C7).
- **i18n**: `src/i18n/*.json`, solo `en.json` va en el bundle inicial
  (`src/i18n/index.ts`); el resto carga bajo demanda.

---

## 3. Resumen de cambios

| # | Cambio | Decisión | Esfuerzo | Toca upstream |
|---|--------|----------|----------|---------------|
| C1 | Ruta `?/open/file/:fileUrl` editable desde URL | D8/D9 | Medio | 1 fichero (`index.ts`) + 1 vista nueva |
| C2 | Extracción de la config de guardado del documento | D9/D10 | Bajo | módulo nuevo |
| C3 | Módulo aislado `LmsBridge.ts` (save/publish/409) | D10 | Medio | módulo nuevo |
| C4 | Botones Guardar/Publicar en la toolbar | D10 | Medio | `LiaScript.vue` (navbar) |
| C5 | Modal de conflicto 409 | D5 | Bajo | componente nuevo |
| C6 | Renovación del token de un solo uso | D9 | Bajo | módulo nuevo + contrato |
| C7 | Ocultar integraciones Git/OAuth y ajustes del menú | D1 | Bajo | `LiaScript.vue` (shareGroups) |
| C8 | `.env` de build y branding FPVirtual | D8 | Bajo | config |
| C9 | i18n (en + es) | — | Bajo | 2 JSON |
| C10 | CI de build y estrategia de rebase | D10 | Bajo | `.github/` |

Principio rector (D10): todo el código propio vive en **ficheros nuevos**
bajo `src/ts/lms/` y `src/components/lms/`; las **incursiones en
ficheros upstream se limitan a 3 puntos** (router, navbar, shareGroups)
para que el rebase periódico sea casi trivial.

---

## 4. Cambios en detalle

### C1 — Ruta de apertura editable desde URL

**Qué**: nueva ruta `?/open/file/:fileUrl` que abre un documento remoto
**en modo edición completa**, a diferencia de `?/show/file/...` que es
solo lectura.

**Cómo se aborda**:

1. Nueva vista `src/views/OpenFile.vue` (espejo de `File.vue`):
   - `fetch(fileUrl)` → markdown (incluye el bloque meta inyectado por
     `content.php`, ver contrato §5).
   - Reutiliza `replaceURLs` / `replaceMacroURLs` de `File.vue` para
     resolver enlaces relativos (extraerlas a `src/ts/urlRewrite.ts`
     para no duplicar).
   - Llama a C2 para extraer la config de guardado.
   - Llama a `createProjectFromFiles(
       [{ path: mainPath, bytes }], { lms })` y navega a
     `?/edit/<storageId>`.
2. Entrada en el router de `src/index.ts` (única línea de ruta nueva).
3. Errores: token caducado/inválido (403 de `content.php`) → pantalla
   con enlace "volver a Moodle" (`return_url` no disponible aún →
   mensaje genérico de reabrir desde el LMS).

**Notas**:

- El proyecto queda persistido en IndexedDB; reabrir la misma URL crea
  un proyecto nuevo (comportamiento deseado: cada sesión de edición
  parte del SHA fresco que sirve `content.php`).
- El nombre del documento principal en el Y.Doc es `README.md`
  (constante en `Editor.vue`); se conserva — el nombre real vive en
  `meta.lms.file` y solo importa al guardar.

### C2 — Extracción de la configuración de guardado

**Qué**: leer del markdown recibido el bloque de configuración y
convertirlo en `meta.lms` del proyecto.

**Cómo se aborda**:

- Nuevo módulo `src/ts/lms/config.ts` con
  `extractLmsConfig(markdown): { lms, strippedMarkdown }`:
  - Localiza el comentario de cabecera LiaScript (`<!-- ... -->`)
    y dentro el bloque YAML con la clave raíz acordada.
  - **Nombre genérico de la clave**: `liascript-lms` (no
    `liascript-moodle`), coherente con D10: cualquier LMS puede
    inyectarla. El plugin seguirá inyectando los mismos campos.
  - Campos: `save_endpoint`, `publish_endpoint?`, `file`, `branch`,
    `sha`, `token`, `token_refresh_endpoint?`, `readonly`,
    `return_url`.
  - **Se elimina el bloque del documento** antes de importarlo
    (`strippedMarkdown`) para que no se compile ni se guarde de vuelta
    en Git; `content.php` lo vuelve a inyectar en cada apertura.
- Parser YAML mínimo propio (el bloque es plano, clave: valor) para no
  añadir dependencia; si crece, `yaml` (~40 kB) lazy-loaded.

### C3 — Módulo aislado `LmsBridge.ts`

**Qué**: toda la lógica de guardado/publicación contra el LMS, en un
único módulo (`src/ts/lms/LmsBridge.ts`), sin tocar el resto del
editor.

**Cómo se aborda**:

```ts
class LmsBridge {
  constructor(cfg: LmsConfig)
  async save(getContent: () => string): Promise<SaveResult>
  async publish(format: "scorm" | "h5p" | "epub" | "pdf"): Promise<PublishResult>
  canSave(): boolean        // !readonly && token válido
  refreshToken(): Promise<void>
}
```

- `save()`: POST JSON a `save_endpoint`
  `{ file, branch, original_sha, content, token }`:
  - `200 { new_sha, token? }` → actualiza `meta.lms.sha` en Dexie (vía
    callback que escribe con `database.put`, siguiendo el patrón de
    `LiaScript.vue:557`) y, si viene, el token renovado (C6).
  - `409 { resolution_branch, diff_url }` → devuelve resultado de
    conflicto para que C5 lo pinte.
  - Errores de red/5xx → resultado de error reintentable.
- `publish()`: fase 2 — POST a `publish_endpoint` `{ file, sha,
  format, token }`; la respuesta la gestiona Moodle (crea el módulo).
  Solo existe si `publish_endpoint` está presente.
- El contenido a guardar es **`getMainValue()`** (documento principal);
  los assets del explorador no se guardan en v1 (ver cuestiones
  abiertas).
- Sin librerías nuevas: `fetch` + tipos TS.

### C4 — Botones Guardar/Publicar en la toolbar

**Qué**: dos botones en la navbar del editor, visibles **solo si el
proyecto tiene `meta.lms`**.

**Cómo se aborda**:

- Nuevo componente `src/components/lms/LmsSaveBar.vue`:
  - Botón **Guardar** (primario): estados `idle → saving → saved |
    error | conflict`; icono Bootstrap Icons coherente con la toolbar
    (`bi-cloud-check`, `bi-arrow-repeat` mientras guarda).
  - Botón **Publicar** (secundario, solo si `publish_endpoint`):
    desplegable con los formatos disponibles.
  - Si `readonly: true` → se muestra un badge "Solo lectura" en lugar
    del botón Guardar.
  - Texto informativo contextual: rama y SHA corto (tooltip), para que
    el profesor vea dónde está guardando.
- Incursión mínima en `LiaScript.vue`: importar el componente y
  renderizarlo en `lia-editbar-right` (antes del botón Compartir),
  pasándole `meta?.meta?.lms`, `getMainValue` vía `$refs.editor` y el
  `database.put` para persistir el nuevo SHA.
- Atajo `Ctrl+S`: hoy compila la vista previa (binding en
  `Editor.vue`). Se mantiene la compilación y **además** dispara
  guardado LMS si hay `meta.lms` (decisión de UX: el profesor espera
  que Ctrl+S "guarde de verdad").

### C5 — Modal de conflicto 409

**Qué**: cuando el guardado devuelve 409 (otro commit entró entre
medias, D5), mostrar opciones claras.

**Cómo se aborda**:

- Nuevo componente `src/components/lms/LmsConflictModal.vue` (usa el
  `Modal.vue` existente como base visual):
  - Mensaje: "El documento cambió en el servidor mientras editabas".
  - Datos: rama de resolución creada y botón **Ver diferencias**
    (`diff_url`, nueva pestaña).
  - Acciones: **Recargar versión actual** (descarta mis cambios:
    re-fetch de `fileUrl` y reemplazo del Y.Text), **Forzar mi
    versión** (reintento con `original_sha` actualizado al HEAD que
    indica la respuesta), **Cancelar**.
- La rama `resolucion/...` que crea el engine conserva el trabajo del
  profesor aunque elija recargar — se indica en el texto del modal.

### C6 — Renovación del token de un solo uso

**Qué**: el token (D9) es de corta duración; una sesión de edición
puede durar horas.

**Cómo se aborda**:

- Contrato (§5): `save.php` devuelve un `token` renovado en cada
  respuesta 200, y opcionalmente existe `token_refresh_endpoint` para
  renovar sin guardar (ping cada N minutos desde `LmsBridge` si hay
  actividad).
- `LmsBridge.refreshToken()` actualiza `meta.lms.token` en Dexie.
- Si el guardado devuelve 401/403 por token caducado: mensaje claro +
  botón "Volver a abrir desde Moodle" (`return_url`), nunca un error
  crudo.

### C7 — Ocultar integraciones Git/OAuth

**Qué**: el profesor no usa GitHub/GitLab (D1); esas entradas del menú
Compartir (Gist, push/pull/publish, grupos GitHub/GitLab) se ocultan
para no confundir y para eliminar los errores de OAuth del fork sin
`.env`.

**Cómo se aborda**:

- Flag de build en `.env`: `LIAEDIT_HIDE_GIT=true` (Parcel inyecta
  `process.env.*`).
- En `shareGroups` (`LiaScript.vue:376-426`): no añadir el grupo `git`
  ni los items `githubGist` si el flag está activo. El bloque queda
  reducido a: colaborar (si se habilita), exportar (zip, exporter,
  descargar .md).
- Se conserva el código upstream intacto tras un `if`, para minimizar
  conflictos de rebase y poder reactivarlo.
- La ayuda (`nav.help`) apunta por defecto a la documentación oficial
  de LiaScript; configurable por `.env` (`LIAEDIT_HELP_URL`) para
  apuntar a la guía de autor propia cuando exista.

### C8 — `.env` de build y branding

**Qué**: configuración de la instancia self-hosted.

**Cómo se aborda** (`.env` del fork, no commiteado; plantilla
`.env.example` sí):

```ini
LIASCRIPT="https://liascript.github.io/course/"
PROXY=""                      # proxy CORS propio si hace falta
LIAEDIT_HIDE_GIT=true
LIAEDIT_HELP_URL=""           # guía de autor interna
# Colaboración desactivada por defecto (cuestión abierta #6):
# SIGNALING_SERVER / WEBSOCKET_SERVER / ICE_SERVERS vacíos
```

- Branding mínimo: logo (`assets/logo.png`) y nombre en
  `manifest.webmanifest`/`index.html`. Sin tocar estilos.
- Documentar en el README del fork cómo construir (`npm ci && npm run
  build` → `dist/`) y desplegar tras Nginx con HTTPS (requisito de la
  PWA y de `fetch` cross-origin).

### C9 — i18n

**Qué**: textos nuevos (botones, estados, modal de conflicto, errores).

**Cómo se aborda**: claves bajo `lms.*` en `src/i18n/en.json` y
`es.json` (los demás idiomas caen al fallback en inglés; se completan
si hay demanda). Nada de texto hardcodeado en los componentes nuevos.

### C10 — CI de build y estrategia de mantenimiento del fork

**Qué**: que el fork sea mantenible en el tiempo (D10).

**Cómo se aborda**:

- Rama de trabajo `main` del fork = upstream + parches; tags
  propios `fpvirtual-vX.Y.Z` por release desplegada.
- **Rebase periódico** sobre `LiaScript/LiveEditor:master` (mensual o
  tras release upstream): los parches propios tocan 3 puntos
  acotados (router, navbar, shareGroups) → conflictos previsibles y
  pequeños.
- GitHub Action en el fork: `npm ci && npm run build` en cada push a
  `main`, artefacto `dist/` descargable (y, en el futuro, despliegue
  automático al servidor del editor).
- Tras estabilizar C1–C4, **proponer el parche upstream** (diseño
  genérico `liascript-lms`): si se acepta, el fork se reduce a
  configuración.

---

## 5. Contrato editor ↔ plugin (recordatorio)

Lo que el fork espera recibir (lo inyecta `content.php` del plugin,
según `desarrollo-liaeditor-moodle-v1.md` §5.1, renombrado a clave
genérica):

```yaml
liascript-lms:
  save_endpoint: https://moodle/local/.../save.php
  publish_endpoint: https://moodle/local/.../publish.php   # opcional (fase 2)
  token_refresh_endpoint: https://moodle/local/.../token.php # opcional
  file: unidad-3.md
  branch: edicion/profesor-x/unidad-3
  sha: b2e4f6a...
  token: <un solo uso, corta duración>
  readonly: false
  return_url: https://moodle/local/.../catalog.php?id=...
```

Y lo que el fork envía:

- `POST save_endpoint` → `{ file, branch, original_sha, content, token }`
  ← `200 { new_sha, token? }` | `409 { resolution_branch, diff_url,
  current_sha }` | `401/403` (token inválido/caducado).
- `POST publish_endpoint` → `{ file, sha, format, token }`
  ← `200 { cmid, url }` | error.

Cualquier cambio de este contrato se hace **primero en el plugin/engine**
y luego se adapta el fork (el plugin es el servidor; el editor, el
cliente).

---

## 6. Hitos

| Hito | Contenido | Criterio de salida |
|------|-----------|--------------------|
| LIV-1 | C1 + C2 (abrir desde URL y leer config) | Abrir `?/open/file/<content.php...>` crea proyecto editable con `meta.lms` correcto |
| LIV-2 | C3 + C4 (guardar) | Editar y pulsar Guardar persiste en la rama vía `save.php`; SHA visible se actualiza |
| LIV-3 | C5 + C6 (conflictos y token) | Un commit externo provoca el modal 409; sesión larga no caduca |
| LIV-4 | C7 + C8 + C9 (producto) | Build con `.env` FPVirtual sin opciones Git, textos en ES |
| LIV-5 | C10 (CI + rebase) | Action verde en `main`; procedimiento de rebase documentado en README del fork |
| LIV-6 | Publish (fase 2) | Botón Publicar crea el módulo en Moodle vía `publish.php` |

Dependencias cruzadas: LIV-1 necesita `content.php` (Fase 1 del
proyecto principal); LIV-2 necesita `save.php` + `/edit/save` del
engine; LIV-6 necesita `publish.php` + `liaex` (Fase 2).

---

## 7. Cuestiones abiertas

1. **Assets del explorador**: en v1 solo se guarda el `.md` principal.
   Si el profesor sube imágenes al proyecto, ¿se envían como multipart
   a `save.php` (el engine las commitea junto al md) o se relega a v2?
2. **`mainPath` fijo**: el documento principal del Y.Doc se llama
   `README.md` por convención interna del editor; el mapeo al nombre
   real (`meta.lms.file`) vive solo en `LmsBridge`. Confirmar que no
   rompe el export zip del menú Compartir (nombra el zip por
   `storageId`, aceptable).
3. **Colaboración**: si en el futuro se activa WebRTC, el guardado
   multi-autor necesita definir de quién es el `token` que se envía
   (propuesta: el del usuario que abrió la sesión; el resto colabora
   sin guardar). Fuera de alcance ahora.
4. **Upstream**: momento y forma exactos de la propuesta (issue previo
   de diseño antes que PR directo, dado el historial del proyecto).

---

## 8. Referencias

- Fork: <https://github.com/FPVirtual/LiveEditor>
- Upstream: <https://github.com/LiaScript/LiveEditor>
- Arquitectura: `docs/desarrollo-liaeditor-moodle-v1.md`
- Especificación original: `docs/cambio-curso-a-liascript.md`
- Ficheros clave del fork: `src/index.ts` (router), `src/views/File.vue`
  (apertura remota), `src/ts/createProject.ts` (creación de proyectos),
  `src/views/LiaScript.vue` (toolbar y shareGroups), `src/ts/Gist.ts`
  (OAuth a ocultar), `src/i18n/` (traducciones)
