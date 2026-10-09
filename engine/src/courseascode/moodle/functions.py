"""Mapeo de las funciones del plugin ``local_courseascode`` (ENG-062).

Este módulo es la **fuente de verdad** del contrato servicio → plugin hasta que
exista el plugin real: cada entrada documenta los parámetros exactos que el
engine envía y la respuesta JSON que espera. El equipo del plugin debe
implementar ``db/services.php`` y ``externallib.php`` para que estos contratos
se cumplan tal cual.

Convenciones del protocolo REST de Moodle web services (los añade
``MoodleRestClient`` a cada llamada, no el plugin):

- Endpoint: ``POST {MOODLE_URL}/webservice/rest/server.php``
- Parámetros comunes: ``wstoken``, ``wsfunction``, ``moodlewsrestformat=json``
- Errores: respuesta 200 con JSON ``{"exception": ..., "errorcode": ..., "message": ...}``

Tipos: ``int`` = entero Moodle, ``string`` = texto, ``data`` = contenido binario
codificado en **base64** (estándar de los web services de Moodle para ficheros),
``datetime`` = ISO 8601.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PluginFunction:
    """Contrato documentado de una función web service consumida por el engine."""

    name: str
    summary: str
    params: str
    returns: str


PLUGIN_FUNCTIONS: dict[str, PluginFunction] = {
    "get_course": PluginFunction(
        name="core_course_get_courses",
        summary="Curso Moodle por ID (función core; la única que no es del plugin).",
        params="options[ids][0]=int (course_id)",
        returns=(
            "Lista con el curso: [{'id': int, 'fullname': str, 'shortname': str, ...}]."
            " Lista vacía = el curso no existe o el token no lo ve."
        ),
    ),
    "upsert_book": PluginFunction(
        name="local_courseascode_upsert_book",
        summary=(
            "Crea el Book del curso si no existe o actualiza nombre/intro/numbering."
            " Idempotente: repetir la llamada no crea un segundo Book."
        ),
        params=(
            "courseid=int, name=string, intro=string (HTML),"
            " numbering=string (none|numbers|bullets|indented)"
        ),
        returns="{'bookid': int}",
    ),
    "upsert_chapter": PluginFunction(
        name="local_courseascode_upsert_chapter",
        summary=(
            "Crea o actualiza el capítulo identificado por su stable id (§17.3)."
            " Repetir la llamada con el mismo stable id actualiza en el mismo capítulo."
        ),
        params=(
            "bookid=int, chapter_stable_id=string, title=string,"
            " content_html=string (HTML renderizado), position=int (1-based)"
        ),
        returns="{} (vacío; el éxito es no-error)",
    ),
    "delete_chapter": PluginFunction(
        name="local_courseascode_delete_chapter",
        summary="Elimina el capítulo por su stable id (§17.2).",
        params="bookid=int, chapter_stable_id=string",
        returns="{} (vacío; error 'chapter_not_found' si el stable id no existe)",
    ),
    "upload_asset": PluginFunction(
        name="local_courseascode_upload_asset",
        summary=(
            "Sube un asset al área de ficheros del Book. Re-subir el mismo filename"
            " sobrescribe (idempotente)."
        ),
        params="bookid=int, filename=string, data=string (base64)",
        returns="{'url': str} — URL pluginfile.php definitiva para referenciar en el HTML",
    ),
    "register_deploy": PluginFunction(
        name="local_courseascode_register_deploy",
        summary=(
            "Inserta una fila en local_courseascode_deploy con todos los campos de §5.3a."
            " No actualiza filas previas: el historial queda intacto."
        ),
        params=(
            "courseid=int, bookid=int, source=string, content_id=string,"
            " content_version=string, git_ref=string, git_commit=string,"
            " content_hash=string, deployed_at=datetime (ISO 8601),"
            " deployed_by=string, status=string"
        ),
        returns="{'id': int} — ID de la fila insertada",
    ),
    "get_deploy": PluginFunction(
        name="local_courseascode_get_deploy",
        summary=(
            "Último despliegue del Book (courseid, source, content_id), el más"
            " reciente por deployed_at. Asunción respecto a §5.3b: el engine"
            " envía también 'source' para desambiguar, pues la tabla clave el"
            " Book por (courseid, source, content_id)."
        ),
        params="courseid=int, source=string, content_id=string",
        returns=(
            "Fila de la tabla como objeto JSON, o null si nunca se desplegó."
            " deployed_at como datetime ISO 8601."
        ),
    ),
    "list_deploys": PluginFunction(
        name="local_courseascode_list_deploys",
        summary=(
            "Todos los despliegues del curso (panel de administración del curso)."
            " Asunción: función adicional a §5.3b que el engine necesita para"
            " ENG-060; confirmar con el equipo del plugin."
        ),
        params="courseid=int",
        returns="Lista de filas de la tabla, más reciente primero",
    ),
}
