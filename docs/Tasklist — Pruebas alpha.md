# Tasklist — Pruebas alpha (Moodle real + contenidos-test)

> Basado en `docs/Sistema-prueba.md`. Cubre la puesta en marcha del entorno de
> pruebas alpha: Moodle `http://192.168.2.253:8088` (Moodle53Beta) y repo de
> contenidos `github.com/FPVirtual/contenidos-test`. IDs `PRU-nnn`.
>
> Referencias: [Especificación v0.2](Especificación%20Moodle%20Course%20as%20Code%20v0.2.md) ·
> [Guía de operación](Guía%20de%20operación.md) · [BITACORA](../BITACORA.md)

## Leyenda

`⬜ pendiente` · `🟡 en curso` · `✅ hecha` · `⏸️ bloqueada`

## Infraestructura y despliegue

- [x] **PRU-001** ✅ Acceso al servidor: SSH `root@192.168.2.253` (config ssh
  existente). El Moodle corre en Docker (`moodle53beta-moodle`, Moodle
  6.0dev). Nota: el servidor responde por **http** (no https) en `:8088`.
  (2026-11-06)
- [x] **PRU-002** ✅ Engine desplegado en el servidor: contenedor
  `courseascode-engine` (red interna del Moodle, alias `courseascode`,
  publicado en `192.168.2.253:8090`), con `/catalog` ya respondiendo.
  Rebuild con `MOODLE_CONNECT_URL` aplicado el 2026-11-09: el engine alcanza
  al Moodle vía el forwarder `cac-moodle-fwd`. Bugs del engine corregidos al
  desplegar: `COURSEASCODE_DB` con ruta pelada rompía SQLAlchemy; al
  Dockerfile le faltaba `git` y la excepción `safe.directory` para
  `/content`.
- [x] **PRU-003** ✅ Plugin instalado: bind mount ya existente
  (`/apps/8088-moodle-v5.3-beta-test/moodle-book-git/plugin` →
  `public/local/courseascode`); código sincronizado por rsync, `php -l` en
  verde y `admin/cli/upgrade.php` aplicado (versión 2026110600). (2026-11-06)
- [x] **PRU-004** ✅ `config.php` configurado:
  `local_courseascode_service_url = http://courseascode:8000` (interna) y
  `local_courseascode_service_public_url = http://192.168.2.253:8090`
  (navegador). **Ojo: config.php no es bind mount; se pierde al recrear el
  contenedor.** (2026-11-06)
- [x] **PRU-005** ✅ Web services ya estaban habilitados (REST + servicio
  `courseascode` con las 9 funciones + token de `svc-courseascode`). Rol
  `courseascodesvc` completado con `webservice/rest:use`,
  `moodle/course:view/update/manageactivities`, `mod/book:read/edit`.
  Token copiado al env del engine sin exponerlo. (2026-11-06)
- [x] **PRU-006** ✅ Las 9 funciones `local_courseascode_*` ejercitadas en el
  ciclo E2E real (2026-11-09): get_course, upsert_book, upsert_chapter,
  delete_chapter, upload_asset, register_deploy, get_deploy, list_deploys,
  get_book, where_deployed (+ `core_course_get_courses`, que faltaba en el
  servicio externo).

## Contenidos (repo `FPVirtual/contenidos-test`)

- [x] **PRU-010** ✅ Semilla del repo: `course.yml` (id `dwes`, título
  "Desarrollo Web en Entorno Servidor") + book `ut03-mvc` (5 capítulos, asset
  SVG, admonitions, enlaces internos) + README. (2026-11-06)
- [x] **PRU-011** ✅ `courseascode validate` en verde sobre el clon local.
  (2026-11-06)
- [x] **PRU-012** ✅ Tag `book/ut03-mvc/v1.0.0` publicado (primera versión
  oficial importable). (2026-11-06)
- [x] **PRU-013** ✅ `GET /catalog` del engine muestra `@dwes/ut03-mvc` v1.0.0
  (verificado en el servidor, 2026-11-06).
- [x] **PRU-014** ✅ v1.1.0 publicada (capítulo 'Para saber más' + nota en
  MVC) y usada en el ciclo UPDATE_AVAILABLE. Al publicar tags nuevos:
  `docker exec courseascode-engine git -C /content fetch --tags` (el clon lo
  escribe el uid 1000 del contenedor). (2026-11-09)

## Usuarios y roles (módulo "Desarrollo Web en Entorno Servidor", DAW)

- [ ] **PRU-020** 🟡 En el Moodle solo existe el curso `CAC-TEST` (id 2) y el
  usuario técnico `svc-courseascode`; no hay curso DWES ni profesores. **Los
  datos los carga el equipo** (2026-11-06). Cuando estén, listar profesores
  con rol en el curso y verificar capabilities.
- [ ] **PRU-021** ⬜ Asignar capabilities del plugin: `viewcatalog` a profesores,
  `deploy` a profesores editores (ya es el default por arquetipo; verificar).
- [ ] **PRU-022** ⬜ Crear/confirmar cuentas de prueba: 1 profesor editor, 1
  profesor no editor (solo preview/catálogo), 1 alumno (no ve nada del plugin).
- [ ] **PRU-023** ⬜ Verificar privacidad §21: el alumno nunca ve metadata Git
  ni las páginas del plugin.

## Ciclo E2E (criterios §32 contra Moodle real — desbloquea ENG-104)

- [x] **PRU-030** ✅ Importación v1.0.0 → `UP_TO_DATE` (2026-11-09, vía API;
  la importación desde la UI del plugin con un profesor queda por probar
  cuando haya usuarios — PRU-020).
- [x] **PRU-031** ✅ UPDATE_AVAILABLE → update → rollback (2026-11-09):
  `status` mostró "disponible: 1.1.0"; update aplicó UPDATE+CREATE sin
  duplicados; rollback a v1.0.0 restauró el estado (sin drift).
- [x] **PRU-032** ✅ Eliminación con confirmación (2026-11-09): el rollback
  sin `confirmed_deletions` omitió el DELETE con warning §17.2; con
  `confirmed_deletions: true` eliminó el capítulo.
- [ ] **PRU-033** ⬜ Hotfix §11.1: `release mark --severity critical --recall`
  sobre v1.0.0 → badge crítico en el panel, redeploy bloqueado (409).
- [ ] **PRU-034** ⬜ Drift §19.1: editar un capítulo a mano en Moodle →
  `DRIFT_DETECTED` en el panel; redeploy lo sobrescribe.
- [ ] **PRU-035** ⬜ `courseascode export --course <id>` genera
  `deployments/<curso>.yml` con el binding real.
- [ ] **PRU-036** ⬜ Activar `make test-integration` (ENG-104) apuntando a este
  Moodle: los 14 tests de integración dejan de skipear.

## Incidencias encontradas (2026-11-06)

0. **2026-11-09 (sesión E2E)** — cadena completa engine→plugin verificada:
   - `svc-courseascode` no estaba "completamente configurado": le faltaban los
     campos de perfil obligatorios del sitio (`cod_centro`, `centro`) —
     rellenados con valores de prueba.
   - El servicio externo no incluía `core_course_get_courses` (la usa el
     engine) — añadida.
   - **Bugs del plugin contra Moodle 6.0 real** (corregidos en el repo):
     `add_module`/`update_module` ya no existen → `add_moduleinfo`/
     `update_moduleinfo`; en update hay que pasar el intro como
     `introeditor` (si no, Moodle lo pisa a null y el UPDATE falla);
     `get_book` debe devolver vacío si el bookid no existe (contrato:
     "null si no existe" — lo usan planner y drift).
   - **Ciclo E2E §32 verificado contra Moodle real**: importación v1.0.0 →
     UP_TO_DATE; redeploy idempotente (0 acciones); v1.1.0 →
     UPDATE_AVAILABLE → update (UPDATE+CREATE); rollback a v1.0.0 con
     eliminación omitida sin confirmación y aplicada con
     `confirmed_deletions` (§17.2); `where_deployed` → [2]. Las 9 funciones
     del contrato ejercitadas.

1. **Caída del Moodle (500 en login/admin, ~12:55)**: la causa NO fue el
   plugin courseascode ni el engine — fue `local/educaaragon` (copiado al
   contenedor ese mismo día a las 12:24, sin bind mount): su `lib.php`
   redeclara `clean_string()`, que ya existe en el core
   (`lib/weblib.php:775`). **Arreglo aplicado en caliente dentro del
   contenedor**: renombrada a `educaaragon_clean_string()` (declaración + 6
   llamadas). ⚠️ Efímero: se pierde al recrear el contenedor — hay que
   subir el fix al repo de ese plugin.
2. **Debug dejado activado** en la BD del Moodle (`debug=32767`,
   `debugdisplay=1`) para poder diagnosticar; con debugdisplay las páginas
   muestran el aviso de deprecación del hook `before_standard_html_head`
   del plugin (Moodle 6.0 quiere el nuevo sistema de hooks — migración
   pendiente, no rompe nada). Si molesta: `php admin/cli/cfg.php
   --name=debugdisplay --set=0`.
3. **Hairpin NAT roto** en el host: los contenedores no alcanzan los puertos
   que el propio host publica. Resuelto con el forwarder `cac-moodle-fwd`
   (socat 192.168.96.10:8088 → moodle:80) + soporte `MOODLE_CONNECT_URL`
   en el engine (Host header = wwwroot público para que no haya 303 y las
   URLs pluginfile salgan correctas).
4. **Bugs del engine detectados al desplegar en Docker** (ya corregidos en
   código): `default_db_url()` no aceptaba rutas peladas; Dockerfile sin
   `git` ni `safe.directory` para `/content`. Endpoint nuevo
   `GET /static/{tema}.css` (el plugin lo enlazaba pero no existía).
5. **CLI del engine en el contenedor**: el clon de contenidos pertenece al
   uid 1000 del contenedor; las actualizaciones de tags deben hacerse con
   `docker exec courseascode-engine git -C /content fetch --tags` (no como
   root en el host, que dejaría ficheros con dueño mezclado).
