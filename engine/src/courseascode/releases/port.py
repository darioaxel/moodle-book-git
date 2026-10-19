"""``SqlReleasePort``: ``ReleasePort`` sobre SQLite (ENG-090/ENG-092).

Es la implementación real que sustituye a ``NullReleasePort`` cuando el
servicio tiene BD configurada (``COURSEASCODE_DB``): el planner (bloqueo
de RECALLED, ENG-075) y el cálculo de estado (badge crítico, ENG-074) leen
aquí sin cambios de código. Además expone ``record_event`` (auditoría,
ENG-095), que ``DeploymentService`` usa si el port la soporta (protocolo
``AuditableReleasePort``, ver ``deployment/releases.py``).
"""

from __future__ import annotations

from courseascode.deployment.releases import ReleasePort
from courseascode.domain.deployment import Severity
from courseascode.domain.semver import SemVer
from courseascode.releases.store import ReleaseStore


class SqlReleasePort(ReleasePort):
    """Consultas de severidad/recall contra la tabla ``releases`` (§11)."""

    def __init__(self, store: ReleaseStore, *, source: str = "dwes") -> None:
        self._store = store
        self._source = source

    def severity_of(self, source: str, book_id: str, version: SemVer) -> Severity | None:
        info = self._store.get(_ref_of(book_id, version), source=source)
        if info is None:
            return None
        return Severity(info.severity)

    def is_recalled(self, source: str, book_id: str, version: SemVer) -> bool:
        info = self._store.get(_ref_of(book_id, version), source=source)
        return info.recalled if info is not None else False

    def record_event(  # noqa: PLR0913 - evento de auditoría: un campo por dimensión
        self,
        event_type: str,
        *,
        actor: str,
        source: str | None = None,
        book_id: str | None = None,
        version: str | None = None,
        detail: dict[str, object] | None = None,
    ) -> None:
        """Auditoría ENG-095: ``DeploymentService`` registra aquí sus deploys."""
        self._store.record_event(
            event_type,
            actor=actor,
            source=source or self._source,
            book_id=book_id,
            version=version,
            detail=detail,
        )


def _ref_of(book_id: str, version: SemVer) -> str:
    return f"book/{book_id}/v{version}"
