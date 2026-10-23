"""Export del binding curso↔versión a ``deployments/<curso>.yml`` (ENG-100, §9).

``deployments/<curso>.yml`` es una **vista exportable** del estado de la tabla
del plugin (``local_courseascode_deploy``): reproducibilidad y auditoría, no la
fuente de verdad — esa sigue siendo la tabla, que es quien resuelve las
importaciones hechas desde la interfaz de Moodle sin tocar Git.

El YAML es determinista: mismo estado del plugin → mismos bytes. Las entradas
van ordenadas por ``(source, content_id)`` y cada una toma el despliegue más
reciente de esa clave (el despliegue *actual*, según ``list_deploys``, que
viene más reciente primero).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from courseascode.moodle.provider import DeployRecord, MoodleProvider

# Versión del formato, por si la vista exportable evoluciona post-beta.
_FORMAT_VERSION = 1


def build_export(moodle: MoodleProvider, courseid: int) -> dict[str, Any]:
    """Construye el dict exportable del curso desde el estado del plugin.

    Falla con ``MoodleError`` (propagada de ``get_course``/``list_deploys``)
    si el curso no existe o Moodle no responde: no se escribe YAML a medias.
    """
    course = moodle.get_course(courseid)
    current: dict[tuple[str, str], DeployRecord] = {}
    for record in moodle.list_deploys(courseid):
        key = (record.source, record.content_id)
        if key not in current:  # list_deploys viene más reciente primero
            current[key] = record
    books = [_record_entry(record) for (_, _), record in sorted(current.items())]
    return {
        "format": f"courseascode-deployments/v{_FORMAT_VERSION}",
        "course": {
            "courseid": course["id"],
            "shortname": course["shortname"],
            "fullname": course["fullname"],
        },
        "books": books,
    }


def export_course(moodle: MoodleProvider, courseid: int, output_dir: Path) -> Path:
    """Escribe ``<output_dir>/<curso>.yml`` y devuelve la ruta escrita.

    ``output_dir`` es relativa al cwd del llamante (la CLI usa
    ``deployments/``). El dump usa ``sort_keys=False`` y las claves en orden
    fijo: el resultado es byte-estable para un mismo estado del plugin.
    """
    document = build_export(moodle, courseid)
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{courseid}.yml"
    text = yaml.safe_dump(
        document,
        sort_keys=False,
        allow_unicode=True,
        default_flow_style=False,
    )
    path.write_text(text, encoding="utf-8")
    return path


def _record_entry(record: DeployRecord) -> dict[str, str]:
    """Entrada de un Book desplegado, con claves en orden fijo (YAML estable)."""
    return {
        "source": record.source,
        "content_id": record.content_id,
        "content_version": record.content_version,
        "git_ref": record.git_ref,
        "git_commit": record.git_commit,
        "deployed_at": record.deployed_at.isoformat(),
        "deployed_by": record.deployed_by,
        "status": record.status,
    }
