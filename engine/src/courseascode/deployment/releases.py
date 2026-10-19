"""Puerto del registro de releases: severidad y recall (ENG-075, §11).

Fase 7 define solo el **protocolo**; la persistencia real (SQLite) llega en
Fase 8 (ENG-090) y sustituirá ``NullReleasePort`` por una implementación que
consulte la tabla de releases. El planner y el cálculo de estado quedan así
integrados y testeables ya: los tests inyectan un port de memoria con
recalls/severidades de ejemplo.

Contrato:

- ``severity_of(source, book_id, version)``: severidad marcada para esa
  versión, o ``None`` si no hay marca (estado UPDATE_AVAILABLE sin badge).
- ``is_recalled(source, book_id, version)``: ``True`` si la versión está
  retirada (bloquea planner y rollback salvo ``--force``, §18).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from courseascode.domain.deployment import Severity
from courseascode.domain.semver import SemVer


class ReleasePort(Protocol):
    """Consultas del ciclo de vida de releases que necesita el engine (ENG-075)."""

    def severity_of(self, source: str, book_id: str, version: SemVer) -> Severity | None:
        """Severidad de la versión, o ``None`` si no está marcada."""
        ...

    def is_recalled(self, source: str, book_id: str, version: SemVer) -> bool:
        """``True`` si la versión está retirada (§18)."""
        ...


@runtime_checkable
class AuditableReleasePort(ReleasePort, Protocol):
    """``ReleasePort`` con auditoría (ENG-095).

    ``DeploymentService`` lo detecta por ``isinstance`` y, cuando el port lo
    soporta (p. ej. ``SqlReleasePort`` con BD configurada), registra cada
    deploy en ``AuditEvent`` con actor = ``deployed_by``. Los ports sin
    persistencia (``NullReleasePort``, los de memoria de los tests) no
    soportan este método y el servicio simplemente no audita.
    """

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
        """Añade un evento a la auditoría append-only (quién/cuándo/qué)."""
        ...


@dataclass(frozen=True)
class NullReleasePort:
    """Implementación por defecto: sin recalls ni severidades (hasta Fase 8)."""

    def severity_of(self, source: str, book_id: str, version: SemVer) -> Severity | None:
        return None

    def is_recalled(self, source: str, book_id: str, version: SemVer) -> bool:
        return False
