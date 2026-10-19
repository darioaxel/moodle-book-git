"""Registro de releases: persistencia SQLite y severidad/recall (§11, ENG-090+).

- ``ReleaseStore``: BD SQLite (idempotente, sesión por operación) con las
  tablas ``releases`` y ``audit_events``.
- ``SqlReleasePort``: ``ReleasePort`` (ENG-075) sobre el store; se inyecta en
  ``DeploymentService`` en vez del ``NullReleasePort`` cuando hay BD.
- ``default_db_url()``: ``COURSEASCODE_DB`` o ``~/.courseascode/courseascode.db``.
"""

from courseascode.releases.models import AuditEvent, ReleaseInfo, ReleaseRow
from courseascode.releases.port import SqlReleasePort
from courseascode.releases.store import (
    DEFAULT_DB_URL,
    ReleaseStore,
    ReleaseStoreError,
    default_db_url,
)

__all__ = [
    "DEFAULT_DB_URL",
    "AuditEvent",
    "ReleaseInfo",
    "ReleaseRow",
    "ReleaseStore",
    "ReleaseStoreError",
    "SqlReleasePort",
    "default_db_url",
]
