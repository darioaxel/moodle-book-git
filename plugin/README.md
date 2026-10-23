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
- Añade una capa de visualización:
  - Catálogo del servicio (`/local/courseascode/catalog.php`).
  - Versiones de un libro (`/local/courseascode/bookversion.php`).
  - Estado de despliegue del sitio (`/local/courseascode/admin.php`).
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
$CFG->local_courseascode_service_url   = 'http://courseascode-service:8080';
$CFG->local_courseascode_service_token = '<token del usuario técnico>'; // opcional
```

- `_service_url`: base del servicio Course as Code (lo que el engine expone en
  `/catalog`, `/catalog/{source}/{book}/versions` y `/deployment/status`). Si
  no está definido, las páginas del plugin muestran un aviso
  (`servicenotconfigured`) en lugar de fallar.
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
- Páginas UI (`catalog.php`, `bookversion.php`, `admin.php`): actualmente son
  esqueletos con sus templates Mustache; completar la presentación.
