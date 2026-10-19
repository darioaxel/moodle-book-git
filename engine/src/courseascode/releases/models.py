"""Modelos de persistencia y de dominio del registro de releases (ENG-090, §11).

Tablas SQLite (SQLModel):

- ``releases``: estado administrativo mutable de cada versión publicada
  (severidad, recall, motivo, quién y cuándo lo marcó). La clave es el
  ref/tag completo ``book/<id>/vX.Y.Z`` junto a su ``source``: el mismo tag
  puede existir en varias fuentes (repo compartido vs fork privado, §26.4).
- ``audit_events``: auditoría append-only de todo lo que pasa por el
  servicio (ENG-095): ``release mark``, deploys y webhooks recibidos.

Los tipos públicos de lectura son pydantic puros (``ReleaseInfo``,
``AuditEvent``): los consumidores (CLI, API, planner) no dependen de
SQLModel.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from sqlmodel import JSON, Column, SQLModel
from sqlmodel import Field as SQLField


def utcnow() -> datetime:
    """Marca temporal consciente de zona (UTC), formato consistente en SQLite."""
    return datetime.now(UTC)


class ReleaseRow(SQLModel, table=True):
    """Fila de ``releases``: severidad/recall de una versión publicada (§11)."""

    __tablename__ = "releases"

    ref: str = SQLField(primary_key=True, description="Tag completo: book/<id>/vX.Y.Z")
    source: str = SQLField(
        primary_key=True, index=True, description="Fuente del contenido (namespace)"
    )
    book_id: str = SQLField(index=True, description="ID estable del Book (book.yml)")
    version: str = SQLField(description="SemVer de la versión (sin prefijo 'v')")
    severity: str = SQLField(default="normal", description="normal | critical")
    recalled: bool = SQLField(default=False, description="RECALLED: bloqueada para nuevos deploys")
    fixed_in: str | None = SQLField(default=None, description="Versión que corrige el problema")
    reason: str | None = SQLField(
        default=None, description="Motivo (obligatorio si critical/recall)"
    )
    marked_by: str = SQLField(min_length=1, description="Quién marcó (rol coordinador)")
    marked_at: datetime = SQLField(default_factory=utcnow, description="Cuándo se marcó")


class AuditEventRow(SQLModel, table=True):
    """Fila de ``audit_events``: quién/cuándo/qué (ENG-095). Append-only."""

    __tablename__ = "audit_events"

    id: int | None = SQLField(default=None, primary_key=True)
    event_type: str = SQLField(index=True, description="p. ej. release.mark | deploy | webhook.git")
    actor: str = SQLField(
        min_length=1, description="Quién: coordinador, deployed_by, git-platform…"
    )
    source: str | None = SQLField(default=None, index=True, description="Fuente afectada")
    book_id: str | None = SQLField(default=None, index=True, description="Book afectado")
    version: str | None = SQLField(default=None, description="Versión afectada")
    detail: dict[str, Any] = SQLField(
        default_factory=dict, sa_column=Column(JSON), description="Payload estructurado del evento"
    )
    at: datetime = SQLField(default_factory=utcnow, index=True, description="Cuándo ocurrió")


class ReleaseInfo(BaseModel):
    """Lectura pública de una fila de ``releases``."""

    model_config = ConfigDict(frozen=True)

    ref: str
    source: str
    book_id: str
    version: str
    severity: str
    recalled: bool
    fixed_in: str | None
    reason: str | None
    marked_by: str
    marked_at: datetime

    @classmethod
    def from_row(cls, row: ReleaseRow) -> ReleaseInfo:
        return cls(
            ref=row.ref,
            source=row.source,
            book_id=row.book_id,
            version=row.version,
            severity=row.severity,
            recalled=row.recalled,
            fixed_in=row.fixed_in,
            reason=row.reason,
            marked_by=row.marked_by,
            marked_at=row.marked_at,
        )


class AuditEvent(BaseModel):
    """Lectura pública de una fila de ``audit_events`` (ENG-095)."""

    model_config = ConfigDict(frozen=True)

    id: int | None
    event_type: str
    actor: str
    source: str | None = None
    book_id: str | None = None
    version: str | None = None
    detail: dict[str, Any] = Field(default_factory=dict)
    at: datetime

    @classmethod
    def from_row(cls, row: AuditEventRow) -> AuditEvent:
        return cls(
            id=row.id,
            event_type=row.event_type,
            actor=row.actor,
            source=row.source,
            book_id=row.book_id,
            version=row.version,
            detail=dict(row.detail),
            at=row.at,
        )
