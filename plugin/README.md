# local_courseascode

Plugin local de Moodle que expone el contrato de "Course as Code": catálogo de
libros versionados y despliegue de contenido en instancias `mod_book` del
curso, controlado por el engine `courseascode-engine` (pista 🧠 del repositorio).

Pensado para **Moodle 5.3+** (`$plugin->requires = 2026100600`).

## Qué hace

- Sirve las 8 funciones propias del contrato (`upsert_book`, `upsert_chapter`,
  `delete_chapter`, `upload_asset`, `register_deploy`, `get_deploy`,
  `list_deploys`, `get_book`, `where_deployed`) como web services REST,
  junto a la función core `core_course_get_courses` que ya existe en Moodle.
- Mantiene el mapping entre **capítulos de `mod_book` y `stable_id`**
  (tabla `local_courseascode_chapter`), para que el engine pueda hacer
  upsert/delete de capítulos de forma idempotente entre despliegues.
- Registra cada despliegue (tabla `local_courseascode_deploy`), de modo que un
  `Book` se identifica por `(courseid, source, content_id)`: `where_deployed`
  devuelve dónde está publicado cada contenido.
- Añade una capa de visualización completa:
  - Catálogo del servicio (`/local/courseascode/catalog.php`, §12.2): tarjetas
    por fuente con resumen, tags, nº de capítulos, última versión, preview
    (ENG-044) y acceso a "Añadir al curso".
  - Página de versión de un Book (`/local/courseascode/bookversion.php`, §21):
    estado §19 con badge de severidad (§11), metadata Git (solo profesores),
    lista de versiones con preview y "Ver cambios" (diff estructural §22 vía
    `POST /deployment/plan`), con confirmación de deploy — incluida la
    confirmación explícita de eliminaciones (§17.2).
  - Acción de despliegue (`/local/courseascode/deploy.php`): solo POST con
    sesskey, exige `local/courseascode:deploy` + `moodle/course:manageactivities`
    (§12.3) y ejecuta `POST /deploy` del servicio.
  - Panel del curso (`/local/courseascode/admin.php`, §23.1): Books
    desplegados con versión publicada/disponible, estado §19 por Book y
    acciones (ver en el curso, preview, actualizar).
  - CSS inyectado solo en páginas `mod-book-view` vía
    `local_courseascode_before_standard_html_head()` para estilizar el
    contenido desplegado.

## Instalación

1. Copiar el directorio `plugin/` como `local/courseascode` dentro de la
   instalación de Moodle.
2. Ejecutar la actualización de base de datos (se crean
   `local_courseascode_deploy` y `local_courseascode_chapter`).
3. Crear un **usuario técnico** para el engine (p. ej. `svc-courseascode`) y
   generarle un **token de servicio web** (`Administration → Server → Manage
   tokens`). La cuenta debe tener en los cursos donde se despliegue:
   - `local/courseascode:deploy` (capítulo 6 de la especificación).
   - `local/courseascode:viewcatalog` en el contexto de sistema para el
     catálogo.
   - Los permisos estándar de `mod/book:edit` y `moodle/course:update`
     implícitos en la edición del curso.

## Configuración

En `config.php` (o equivalente):

```php
$CFG->local_courseascode_service_url        = 'http://courseascode-service:8080';
$CFG->local_courseascode_service_public_url = 'http://moodle.example.com:8090'; // opcional
$CFG->local_courseascode_service_token      = '<token del usuario técnico>';   // opcional
```

- `_service_url`: base del servicio Course as Code para las llamadas
  **server-to-server** (lo que el engine expone en `/catalog`,
  `/catalog/{source}/{book}/versions`, `/deployment/*`). Si no está definido,
  las páginas del plugin muestran un aviso (`servicenotconfigured`) en lugar
  de fallar.
- `_service_public_url`: base del servicio para los enlaces que abre el
  **navegador** del usuario (preview de Books, CSS del tema en
  `mod-book-view`). En despliegues donde el servicio vive en una red interna
  (Docker), la URL interna no resuelve para el profesor: definir aquí la URL
  pública. Si no se define, se usa `_service_url`.
- `_service_token`: se envía como cabecera `X-CourseAsCode-User` en las
  llamadas del servidor a ese servicio.

## Contrato con el engine

El contrato exacto (nombres de función, parámetros y formas de retorno) está
cotejado con `engine/src/courseascode/moodle/functions.py`. Convenciones:

- Errores: `{exception: {errorcode, message}}`.
- Assets en base64 vía `upload_asset`; se guardan en el área
  `local_courseascode/asset` y se sirven con `pluginfile.php`.
- `deployed_at` en ISO 8601 hacia el engine (el plugin lo almacena en epoch y
  lo serializa con `gmdate('c')`).
- `get_deploy` devuelve el despliegue más reciente por `deployed_at` (o sin
  la clave `deploy` si no hay ninguno).

Las clases externas viven en `classes/external/` con el classname estilo
Moodle 5.x (`local_courseascode\external\<nombre>`), declaradas en
`db/services.php`.

## Decisiones de diseño

- **Capítulos en `mod_book` + tabla de mapping**: el engine trabaja con
  `stable_id` estables; Moodle con `chapterid` numéricos. La tabla
  `local_courseascode_chapter` (UNIQUE `bookid + stable_id`) desacopla ambos
  mundos y permite upsert/delete idempotente.
- **Book identificado por `(courseid, source, content_id)`** vía tabla
  `local_courseascode_deploy`, no por nombre ni por id de instancia.
- **Estado del despliegue** (`status`, `git_ref`, `git_commit`,
  `content_hash`) queda en el lado del plugin/servicio; el engine solo lo
  registra con `register_deploy`.

## Pendientes

- Validar la forma exacta del "sin resultado" en `get_deploy` contra el
  parser del engine (`engine/src/courseascode/moodle/rest_client.py`): si el
  parser exige la clave ausente o `null`, ajustar la respuesta.
- `php -l` y pruebas de integración contra un Moodle real (moodle-docker):
  **este entorno no tiene PHP**; queda para el entorno con Moodle.
- Versiones RECALLED (§11): la UI muestra el 409 del engine con su mensaje;
  el despliegue forzado (`force: true`) queda solo en la CLI del coordinador,
  sin botón en la web.
- Selección de sección del curso al añadir un Book (§12.3 paso 3): el contrato
  `POST /deploy` de la Beta no la admite; los Books se crean en la sección 0.
