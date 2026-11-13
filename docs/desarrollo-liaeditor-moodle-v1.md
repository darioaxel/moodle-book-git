# Desarrollo LiaEditor–Moodle v1

**Versión**: 1.0-draft
**Fecha**: 2026-11-12
**Estado**: En estudio — decisiones de arquitectura tomadas, pendiente plan de implementación
**Documento base**: `cambio-curso-a-liascript.md` (especificación `mod_liamd` v0.1.0)

---

## 1. Propósito

Recoger las decisiones de arquitectura tomadas para migrar el sistema
"Course as Code" (hoy basado en `mod_book`) a un flujo basado en
**LiaScript + LiaEdit (LiveEditor)**, donde:

- El repositorio Git sigue siendo la única fuente de verdad.
- La edición se hace en LiaEdit (LiveEditor de LiaScript) self-hosted.
- La exportación a formatos (SCORM, H5P, ePub, PDF) se apoya en el
  ecosistema LiaScript (exporter en navegador y/o `liaex` server-side).
- El plugin Moodle gestiona los markdown que recibe de Git, el guardado
  transparente y la trazabilidad de qué versión está publicada en cada curso.

Este documento sustituye a las partes de `cambio-curso-a-liascript.md` que
quedan revisadas por estas decisiones.

---

## 2. Punto de partida

### 2.1 Arquitectura actual

- **`plugin/` (`local_courseascode`)**: plugin local de Moodle que crea
  instancias `mod_book` y capítulos HTML vía web services
  (`upsert_book`, `upsert_chapter`, `delete_chapter`, `upload_asset`,
  `register_deploy`, `get_deploy`, `list_deploys`, `get_book`,
  `where_deployed`). Mantiene mapping `stable_id ↔ chapterid`
  (`local_courseascode_chapter`) y registro de despliegues
  (`local_courseascode_deploy`). UI: catálogo, página de versión, deploy,
  panel de curso.
- **`engine/` (FastAPI, Python)**: cliente Git, render Markdown→HTML,
  planner/executor de despliegues, API de catálogo. Es el único que
  habla con Git y con los web services del plugin.

### 2.2 Referencias externas verificadas

- **LiaEdit / LiveEditor**: app 100% navegador (PWA), build estático
  (`npm run build` → `dist/`), configurable vía `.env` en build
  (URL base LiaScript, OAuth GitHub, proxy CORS, WebRTC).
  Repositorio: <https://github.com/LiaScript/LiveEditor>.
  **No tiene API de plugins para la UI** ni API pública para leer el
  documento desde fuera (el "plugin support" anunciado se refiere a
  macros del lenguaje LiaScript).
- **LiaScript-Exporter**: corre como app web en el navegador y LiaEdit
  puede entregarle el curso directamente. Formatos: SCORM 1.2/2004, IMS,
  xAPI, H5P, Web, PDF, ePub, DOCX, Android APK.
  Repositorio: <https://github.com/LiaScript/LiaScript-Exporter>.
  También disponible como CLI npm `@liascript/exporter` y GitHub Action.
- LiaEdit **no** soporta guardado contra backends propios de forma
  nativa: su integración de guardado es GitHub (OAuth del usuario) o
  descarga local.

---

## 3. Decisiones de arquitectura (tomadas)

| # | Decisión | Elección | Motivo |
|---|----------|----------|--------|
| D1 | Gestión Git | **Transparente para el profesor**: commit con token de servidor, sin cuentas personales | El profesorado no debe necesitar cuenta GitHub/GitLab |
| D2 | Dónde vive la lógica Git | **En el engine** (cliente Git existente) | No duplicar cliente Git, credenciales ni caché en PHP |
| D3 | Guardado desde el editor | **`save.php` del plugin** como fachada que delega en el engine | El plugin queda en medio del guardado → conoce el SHA resultante → habilita trazabilidad |
| D4 | Ramas de edición | `edicion/<username>/<archivo>`, una por usuario y archivo | Aislamiento de cambios; `main` protegido |
| D5 | Conflictos | Optimistic locking por SHA; en conflicto, rama `resolucion/<user>/<timestamp>-<archivo>` + respuesta 409 | El último escritor no gana silenciosamente |
| D6 | Trazabilidad | **Paso "Publicar en el curso" dentro del plugin**: el profesor sube el artefacto y el plugin crea el módulo (`mod_scorm` / `mod_h5pactivity` / recurso) y registra curso↔SHA↔cmid | Sin este paso, la subida manual rompería el vínculo versión↔curso |
| D7 | Exportación de artefactos | Fase 1: exporter en navegador (nativo de LiaEdit) + subida en el paso Publicar. Fase 2: `liaex` server-side en el engine | Fase 1 no requiere fork; fase 2 da publicación en un clic |
| D8 | Editor | **LiaEdit self-hosted** en dominio propio | El LiveEditor público no se puede modificar; self-hosted elimina dependencia externa y habilita D10 |
| D9 | Autenticación editor↔plugin | **Token de un solo uso** de corta duración ligado a usuario+fichero+rama (no cookies de sesión) | Las cookies Moodle (`SameSite=Lax`) no viajan en fetch cross-origin |
| D10 | Botones en el editor | **Fork con parche mínimo y genérico** (vía B, §6.2) | No existe API de plugins del editor; el fork estático es de bajo mantenimiento |

Decisiones de la especificación original que quedan **descartadas**:

- Cliente Git en PHP dentro de `mod_liamd` (→ lo hace el engine, D2).
- Token de Git en `config_plugins` de Moodle (→ solo en el engine, D2).
- Generación de artefactos como adhoc task de Moodle llamando a
  `docker run` desde el servidor web (→ engine, D7).
- OAuth de GitHub del profesor para guardar (→ token servidor, D1).

---

## 4. Arquitectura resultante

```
┌──────────────────────────── MOODLE ────────────────────────────┐
│  plugin (evolución de local_courseascode)                      │
│  ┌──────────────┐ ┌──────────────┐ ┌───────────────────────┐  │
│  │ Catálogo/UI  │ │ content.php  │ │ save.php / publish.php│  │
│  │ (existente)  │ │ (proxy md)   │ │ (fachada → engine)    │  │
│  └──────────────┘ └──────────────┘ └───────────────────────┘  │
│  ┌──────────────────────────────────────────────────────────┐ │
│  │ Paso "Publicar": crea mod_scorm / mod_h5pactivity /      │ │
│  │ recurso + registra (courseid, file, sha, tipo, cmid)     │ │
│  └──────────────────────────────────────────────────────────┘ │
└──────────────────────────────┬─────────────────────────────────┘
                               │ server-to-server (existente)
┌──────────────────────────────▼─────────────────────────────────┐
│  ENGINE (FastAPI)                                              │
│  Cliente Git (token servidor) · ramas edicion/* · conflictos   │
│  Endpoints nuevos: /edit/content, /edit/save, /publish         │
│  Fase 2: liaex (Docker) para SCORM/H5P/ePub/PDF                │
└──────────────────────────────┬─────────────────────────────────┘
                               │ HTTPS API Git
┌──────────────────────────────▼─────────────────────────────────┐
│  GIT (GitHub/GitLab) — única fuente de verdad                  │
└────────────────────────────────────────────────────────────────┘
                               ▲
┌──────────────────────────────┴─────────────────────────────────┐
│  LIAEDIT SELF-HOSTED (liascript-editor.dominio.com)            │
│  Fase 1: sin modificar (carga ?url=content.php, export nativo) │
│  Fase 2: fork con parche mínimo → botones Guardar/Publicar     │
└────────────────────────────────────────────────────────────────┘
```

---

## 5. Flujos

### 5.1 Edición y guardado

1. Profesor pulsa "Editar" en el catálogo del plugin.
2. El engine crea (o reutiliza) la rama `edicion/<user>/<file>` desde `main`.
3. El plugin genera un **token de un solo uso** (usuario+fichero+rama,
   caducidad corta) y redirige a LiaEdit:
   `https://liascript-editor.dominio.com/?url=<content.php?...&token=...>`
4. `content.php` valida el token, pide el contenido al engine y responde
   el markdown con el bloque YAML inyectado:

   ```yaml
   liascript-moodle:
     save_endpoint: https://moodle/.../save.php
     publish_endpoint: https://moodle/.../publish.php   # fase 2
     branch: edicion/profesor-x/unidad-3
     sha: b2e4f6a...
     token: <mismo token o renovado>
     readonly: false
   ```

5. El profesor edita y guarda → POST a `save.php`
   `{file, branch, original_sha, content, token}`.
6. `save.php` valida token/capacidad → delega en el engine:
   - Si `current_sha == original_sha`: commit con token de servidor →
     `200 {new_sha}`.
   - Si difiere: crea rama `resolucion/...`, commitea ahí →
     `409 {resolution_branch, diff_url}`.
7. El plugin registra la sesión de edición: usuario, fichero, rama,
   `new_sha`. **Aquí queda identificada la versión modificada antes y
   después del commit.**

### 5.2 Publicación (trazabilidad curso↔versión)

**Fase 1 (exporter en navegador):**

1. El profesor, desde LiaEdit, usa la integración nativa con el exporter
   del navegador y descarga SCORM/H5P/ePub/PDF.
2. Vuelve a Moodle → página "Publicar" del plugin: selecciona el `.md`
   (el plugin muestra la última versión guardada por él, `new_sha`),
   sube el artefacto y elige curso/sección.
3. El plugin crea o actualiza el módulo (`mod_scorm` para SCORM,
   `mod_h5pactivity` para H5P, recurso archivo para ePub/PDF) y registra
   la fila de despliegue: `courseid, file, git_commit (sha), tipo, cmid`.

**Fase 2 (server-side, un clic):**

1. Botón "Publicar en Moodle" en el fork de LiaEdit →
   `POST publish.php {file, sha, formato, token}`.
2. El engine ejecuta `liaex` (Docker) y devuelve el artefacto.
3. El plugin crea/actualiza el módulo y registra el despliegue.
   Sin descarga ni subida manual.

### 5.3 Estado de versión en el curso

El estado pasa a ser una comparación trivial de SHAs (sin renderizar
ni diff estructural):

- `UP_TO_DATE`: SHA publicado == HEAD del fichero en su rama.
- `UPDATE_AVAILABLE`: HEAD ha avanzado (commits en `main` o en la rama
  de edición vinculada).
- Se muestra en el panel del curso (equivalente al `admin.php` actual).

---

## 6. Integración con LiaEdit self-hosted

### 6.1 Lo que sabemos del editor

- App estática navegador (PWA), build con `npm run build`, deploy =
  servir `dist/` (Nginx/Caddy, HTTPS necesario).
- `.env` de build permite: apuntar a instancia propia de la web
  LiaScript, proxy CORS propio, OAuth GitHub propio (no lo usaremos, D1),
  servidores WebRTC/TURN para colaboración.
- **Sin API de plugins de UI ni API de lectura del documento.**

### 6.2 Vías para los botones Guardar/Publicar (evaluadas)

| Vía | Descripción | Veredicto |
|-----|-------------|-----------|
| A. Inyección de script al servir (`sub_filter` Nginx / build step) | "Plugin privado" de facto: script propio que pinta botones y extrae el contenido del estado interno (IndexedDB/Yjs) | Frágil ante actualizaciones upstream; solo si se quiere evitar fork a toda costa |
| **B. Fork con parche mínimo y genérico** | Fork del repo; un componente aislado que lee `save_endpoint`/`publish_endpoint` del front matter y añade los botones; fetch a esos endpoints | **Elegida (D10)**. Mantenimiento = rebase periódico de un parche pequeño |
| C. Wrapper en iframe con toolbar propia | Cero modificaciones del editor | Descartada: sin `postMessage` API no se puede leer el contenido → no se puede guardar |

### 6.3 Estrategia del parche

- Diseño **genérico, no específico de Moodle**: "si el documento declara
  `save_endpoint` en su metadata, mostrar botón Guardar contra ese
  endpoint". Válido para cualquier LMS.
- Candidato a proponer **upstream** al proyecto LiaScript; si se acepta,
  el fork desaparece.
- Mientras tanto: fork propio, rebase periódico, parche en un único
  módulo para minimizar conflictos.

---

## 7. Cambios sobre el sistema actual

### 7.1 Plugin Moodle

**Se conservan (casi igual):**

- UI de catálogo y panel de curso.
- Cliente server-to-server al engine (`local_courseascode_service_*`).
- Tabla de despliegues, simplificada (§7.3).
- `upload_asset` pasa a recibir artefactos (zip/h5p/epub/pdf).

**Se eliminan:**

- `upsert_book`, `upsert_chapter`, `delete_chapter` y la tabla
  `local_courseascode_chapter` (ya no hay capítulos; el contenido es un
  `.md` identificado por SHA).
- Hook CSS `mod-book-view` (`before_standard_html_head`): LiaScript
  renderiza client-side, el theme del engine deja de aplicar.

**Se añaden:**

- `content.php` — proxy de contenido con token de un solo uso, CORS
  restringido al dominio del editor, inyección del bloque
  `liascript-moodle`.
- `save.php` — fachada de guardado (valida token/capacidad, delega en
  engine, registra sesión de edición).
- Página "Publicar" — upload de artefacto + creación de módulo
  (`mod_scorm` / `mod_h5pactivity` / `mod_resource`) + registro de
  despliegue.
- `publish.php` — fase 2, publicación server-side en un clic.
- Tabla de sesiones de edición (usuario, fichero, rama, último SHA).
- Capacidades nuevas: `edit`, `editmain` (editar `main` directamente).

### 7.2 Engine

**Se conservan:** cliente Git, catálogo, API server-to-server.

**Se añaden:**

- `GET /edit/content` — contenido del fichero en rama + SHA actual.
- `POST /edit/save` — verificación de SHA, commit, manejo de conflicto
  con rama `resolucion/...`.
- Gestión de ramas `edicion/<user>/<file>` (creación, reset a main,
  detección de "stale" si el fichero se renombra en `main`).
- Fase 2: `POST /publish` — wrapper de `liaex` (Docker) para
  SCORM/H5P/ePub/PDF.

**Se simplifica:** el planner de despliegues deja de comparar capítulo
a capítulo; compara SHAs de fichero. La carpeta `deployment/` queda en
desuso para el flujo nuevo (conservar solo si hay books legados).

### 7.3 Modelo de datos (plugin)

Tabla de despliegues adaptada (sustituye a `local_courseascode_deploy`):

| Campo | Descripción |
|-------|-------------|
| `courseid` | Curso |
| `source_file` | Ruta del `.md` en el repo |
| `git_commit` | SHA publicado (40 chars) |
| `artifact_type` | `scorm` \| `h5p` \| `epub` \| `pdf` |
| `cmid` | Módulo creado en el curso |
| `deployed_at` / `deployed_by` | Auditoría |
| `status` | `ok` \| `error` |

Tabla de sesiones de edición (`liamd_edit` de la especificación
original): usuario, fichero, rama, `opened_at`, `last_save`,
`closed_at`, último `new_sha` conocido (alimenta el paso Publicar).

---

## 8. Detalles técnicos críticos

1. **SameSite / CORS**: las cookies de sesión de Moodle no viajan en el
   fetch cross-origin del editor → autenticación por **token de un solo
   uso** generado en la redirección de edición, ligado a
   usuario+fichero+rama, caducidad corta. CORS con
   `Access-Control-Allow-Origin` = dominio del editor, sin credenciales.
2. **Repo privado**: el editor no puede leer raw de un repo privado; el
   proxy `content.php` resuelve autenticación y es imprescindible.
3. **Límites**: `.md` máx 1 MB; rate limiting en `content.php` y
   `save.php` (60 req/min por usuario); sanitización de rutas contra
   path traversal.
4. **Conflictos**: respuesta 409 con rama `resolucion/...` y URL de
   diff; la UI del plugin ofrece las opciones de resolución (abrir diff,
   recargar versión actual, forzar guardado).
5. **PDF server-side** (fase 2): `liaex --format pdf` usa
   Puppeteer/Chromium → contenedor con `--shm-size=1g` y cola con más
   recursos.

---

## 9. Fases

### Fase 1 — MVP funcional (sin fork)

- `content.php` + token de un solo uso + CORS.
- `save.php` + endpoints `/edit/*` del engine (ramas, conflictos, commit
  con token servidor).
- Tabla de sesiones de edición + tabla de despliegues simplificada.
- Página "Publicar": subida de artefacto + creación de módulo + registro.
- Deploy de LiaEdit self-hosted **sin modificar**.
- Flujo del profesor: editar → guardar (botón del editor vía metadata;
  si el editor público no lo permite, userscript opcional) → exportar
  en navegador → subir en página Publicar.

### Fase 2 — Un clic (fork)

- Fork de LiaEdit con parche mínimo genérico (Guardar + Publicar).
- `POST /publish` en el engine con `liaex` (Docker): SCORM, H5P, ePub, PDF.
- El paso Publicar pasa a ser opcional (retrocompatible) o se elimina la
  subida manual.
- Valorar contribuir el parche upstream.

### Fase 3 — Producción

- Monitorización y logs de commits/publicaciones.
- Limpieza de sesiones de edición abandonadas (cron).
- Documentación de usuario (profesorado).
- Pruebas de carga.

---

## 10. Cuestiones abiertas

1. **Botón Guardar en fase 1**: el LiaEdit self-hosted sin modificar
   ¿permite algún hook de guardado configurable, o es imprescindible el
   userscript hasta la fase 2? Verificar leyendo el código del repo
   (búsqueda de `save` / `gist` / `github` en la toolbar).
2. **Exporter embebible**: si en fase 2 interesara generar el artefacto
   en el navegador en vez de server-side, ¿es `@liascript/exporter`
   usable como librería con API programática? Requiere prueba de
   concepto. Por defecto se asume server-side (D7).
3. **H5P**: confirmar que el formato H5P del exporter encaja con
   `mod_h5pactivity` de Moodle (tipo de paquete y tracking).
4. **SCORM embebido vs. referenciado**: decidir `--scorm-embed`
   (contenido dentro del zip, recomendado para portabilidad).
5. **Books legados**: ¿se mantiene el flujo `mod_book` actual en
   paralelo durante la transición o se migra todo de una vez?
6. **Colaboración WebRTC de LiaEdit**: ¿se habilita edición colaborativa
   entre profesores (requiere servidor de señalización/TURN propio) o se
   desactiva?

---

## 11. Referencias

- Especificación original: `docs/cambio-curso-a-liascript.md`
- LiaEdit / LiveEditor: <https://github.com/LiaScript/LiveEditor>
- LiaScript-Exporter: <https://github.com/LiaScript/LiaScript-Exporter>
- Exporter npm: <https://www.npmjs.com/package/@liascript/exporter>
- Documentación LiaScript: <https://liascript.github.io/>
- Plugin actual: `plugin/README.md`
- Contrato engine↔plugin actual: `engine/src/courseascode/moodle/functions.py`
