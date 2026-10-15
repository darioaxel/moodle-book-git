"""``content_hash`` del HTML desplegado (ENG-073, §19.1).

Serialización elegida: **diccionario estable → hash**, persistido como JSON
compacto con claves ordenadas::

    {"introduccion": "sha256…", "mvc": "sha256…", …}

Frente a un único hash agregado, el diccionario permite:

- detectar *qué* capítulo driftó comparando claves (base del mensaje de §19.1);
- recalcular el hash tras un deploy parcial sin necesidad de todos los HTML.

El hash es sha256 del HTML final tal como se despliega en Moodle (segunda
pasada de render, ENG-072, incluida la resolución de placeholders de enlaces
que hace el executor).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping


def hash_bytes(data: bytes) -> str:
    """sha256 hexadecimal de unos bytes (assets, ENG-072)."""
    return hashlib.sha256(data).hexdigest()


def hash_html(html: str) -> str:
    """sha256 hexadecimal del HTML de un capítulo."""
    return hash_bytes(html.encode("utf-8"))


def hashes_of(chapters: Iterable[tuple[str, str]]) -> dict[str, str]:
    """``stable_id → sha256(html)`` para una lista de ``(stable_id, html)``."""
    return {stable_id: hash_html(html) for stable_id, html in chapters}


def serialize_hashes(hashes: Mapping[str, str]) -> str:
    """Serializa el diccionario de hashes como JSON compacto ordenado."""
    return json.dumps(dict(hashes), sort_keys=True, separators=(",", ":"))


def deserialize_hashes(raw: str) -> dict[str, str]:
    """Invierte ``serialize_hashes``; ``ValueError`` si el formato no es válido."""
    data = json.loads(raw)
    if not isinstance(data, dict) or not all(
        isinstance(key, str) and isinstance(value, str) for key, value in data.items()
    ):
        msg = f"content_hash con formato inesperado (se esperaba dict str→str): {raw!r}"
        raise ValueError(msg)
    return dict(data)
