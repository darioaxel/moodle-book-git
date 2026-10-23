"""Logging estructurado con correlation id por operación (ENG-101).

Trazabilidad CLI ↔ API ↔ Moodle: cada ``deploy`` fija un **correlation id**
(contextvar, uuid corto) que structlog inyecta en todos los eventos del
pipeline, y la API lo acepta por el header ``X-Correlation-Id`` (si no llega,
lo genera). Así los eventos ``deploy.start``/``deploy.plan``/``deploy.execute``
de un mismo despliegue se pueden cruzar con los logs del servicio y de Moodle.

Formato de salida (``COURSEASCODE_LOG_FORMAT``):

- ``console`` (por defecto): salida legible para el desarrollador local (CLI).
- ``json``: una línea JSON por evento, para el servicio en producción
  (recolección por el sistema de logs de la plataforma).

La configuración es idempotente: ``configure_logging()`` puede llamarse en el
arranque del CLI y de la app sin efectos adversos. Los tests capturan eventos
en memoria con ``structlog.testing.capture_logs`` (la configuración global se
resuelve de forma perezosa por evento, así la captura funciona igual).
"""

from __future__ import annotations

import contextvars
import os
import uuid
from collections.abc import Iterator
from contextlib import contextmanager

import structlog
from structlog import contextvars as structlog_contextvars

#: Correlation id de la operación en curso (``None`` fuera de deploy/request).
correlation_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "correlation_id", default=None
)

_CORRELATION_ID_LENGTH = 8  # uuid corto: suficiente por operación, legible en logs


def new_correlation_id() -> str:
    """Genera un correlation id corto (uuid4, 8 hex) para una operación."""
    return uuid.uuid4().hex[:_CORRELATION_ID_LENGTH]


@contextmanager
def bound_correlation(cid: str | None = None) -> Iterator[str]:
    """Fija el correlation id para el contexto (deploy CLI, petición API…).

    Si ``cid`` es ``None`` genera uno nuevo. El id queda visible en los
    eventos structlog (vía contextvars) y en la contextvar ``correlation_id``.
    """
    effective = cid or new_correlation_id()
    token = correlation_id.set(effective)
    with structlog_contextvars.bound_contextvars(correlation_id=effective):
        try:
            yield effective
        finally:
            correlation_id.reset(token)


def configure_logging(fmt: str | None = None) -> None:
    """Configura structlog; el formato se toma de ``COURSEASCODE_LOG_FORMAT``.

    Valores: ``console`` (por defecto) o ``json``. Valor desconocido → console.
    """
    effective = (fmt or os.environ.get("COURSEASCODE_LOG_FORMAT") or "console").lower()
    renderer: object
    if effective == "json":
        renderer = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer()
    structlog.configure(
        processors=[
            structlog_contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.StackInfoRenderer(),
            renderer,
        ],
        cache_logger_on_first_use=False,  # los tests capturan eventos en memoria
    )
