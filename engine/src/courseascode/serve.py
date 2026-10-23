"""Arranque del servicio web (ENG-105).

Sirve la app FastAPI (preview + catálogo + deployment + releases) con uvicorn,
configurada por entorno:

- ``CONTENT_REPO`` (obligatoria): ruta al repo de contenidos (working tree).
- ``MOODLE_URL`` / ``MOODLE_TOKEN`` (opcionales): habilitan los endpoints de
  despliegue contra Moodle real; sin ellos responden 503.
- ``COURSEASCODE_DB``: BD de releases/auditoría (default
  ``~/.courseascode/courseascode.db``; en Docker, monta un volumen).
- ``COURSEASCODE_WEBHOOK_SECRET`` / ``COURSEASCODE_ADMIN_TOKEN``: webhook y
  auditoría (ENG-091/093).
- ``HOST`` / ``PORT``: interfaz y puerto de uvicorn (defaults 0.0.0.0:8000).

Uso local: ``CONTENT_REPO=/ruta/al/repo python -m courseascode.serve``.
"""

from __future__ import annotations

import os
from pathlib import Path

import uvicorn
from fastapi import FastAPI

from courseascode.moodle.rest_client import MoodleRestClient
from courseascode.releases.store import ReleaseStore, default_db_url
from courseascode.web import create_app


def build_app() -> FastAPI:
    """Construye la app del servicio desde las variables de entorno."""
    content_repo = os.environ.get("CONTENT_REPO")
    if not content_repo:
        msg = "error: define CONTENT_REPO (ruta al repo de contenidos)"
        raise SystemExit(msg)

    moodle: MoodleRestClient | None = None
    url = os.environ.get("MOODLE_URL")
    token = os.environ.get("MOODLE_TOKEN")
    if url and token:
        moodle = MoodleRestClient(url.rstrip("/"), token)

    return create_app(
        Path(content_repo),
        moodle=moodle,
        store=ReleaseStore(default_db_url()),
        webhook_secret=os.environ.get("COURSEASCODE_WEBHOOK_SECRET"),
        admin_token=os.environ.get("COURSEASCODE_ADMIN_TOKEN"),
    )


def main() -> None:
    """Sirve la app con uvicorn (host/puerto por entorno)."""
    app = build_app()
    uvicorn.run(
        app,
        host=os.environ.get("HOST", "0.0.0.0"),
        port=int(os.environ.get("PORT", "8000")),
    )


if __name__ == "__main__":
    main()
