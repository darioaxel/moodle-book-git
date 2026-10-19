"""``ReleaseStore``: persistencia SQLite del registro de releases (ENG-090).

Una instancia = una base de datos (URL SQLAlchemy, p. ej.
``sqlite:////home/op/.courseascode/courseascode.db``). La inicialización es
idempotente (``SQLModel.metadata.create_all``: crea las tablas si no
existen, no toca lo que haya) y cada operación abre su propia sesión, así
que varias instancias sobre el mismo fichero conviven (proceso CLI +
servicio web).

Ruta por defecto (documentada): ``~/.courseascode/courseascode.db``,
configurable con la variable de entorno ``COURSEASCODE_DB`` (ver
``default_db_url()``).
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import cast

from sqlalchemy import Column
from sqlmodel import Session, SQLModel, create_engine, select

from courseascode.domain.deployment import Severity
from courseascode.domain.semver import SemVer
from courseascode.releases.models import (
    AuditEvent,
    AuditEventRow,
    ReleaseInfo,
    ReleaseRow,
)

DEFAULT_DB_PATH = Path("~/.courseascode/courseascode.db").expanduser()
DEFAULT_DB_URL = f"sqlite:///{DEFAULT_DB_PATH}"


def default_db_url() -> str:
    """URL de la BD por defecto: ``COURSEASCODE_DB`` o ``~/.courseascode/``."""
    return os.environ.get("COURSEASCODE_DB") or DEFAULT_DB_URL


class ReleaseStoreError(RuntimeError):
    """Operación inválida sobre el store (ref mal formado, severidad desconocida…)."""


class ReleaseStore:
    """Almacén SQLite de releases y auditoría (ENG-090/ENG-095)."""

    def __init__(self, db_url: str) -> None:
        self._db_url = db_url
        if db_url.startswith("sqlite:///") and not db_url.startswith("sqlite:////"):
            # sqlite:///relativa → absoluta respecto al directorio actual, para
            # que "mismo fichero" signifique lo mismo desde cualquier cwd.
            raw = db_url.removeprefix("sqlite:///")
            if not Path(raw).is_absolute():
                db_url = f"sqlite:///{Path(raw).resolve()}"
        if db_url.startswith("sqlite:///") and db_url != "sqlite:///:memory:":
            # El directorio de la BD (p. ej. ~/.courseascode/) puede no existir.
            Path(db_url.removeprefix("sqlite:///")).expanduser().parent.mkdir(
                parents=True, exist_ok=True
            )
        # check_same_thread=False: el pool de FastAPI puede tocar la BD desde
        # distintos hilos; cada sesión sigue siendo de un solo uso.
        self._engine = create_engine(db_url, connect_args={"check_same_thread": False})
        SQLModel.metadata.create_all(self._engine)

    @property
    def db_url(self) -> str:
        return self._db_url

    @contextmanager
    def _session(self) -> Iterator[Session]:
        with Session(self._engine) as session:
            yield session

    # -- releases (§11) -----------------------------------------------------------

    def mark(  # noqa: PLR0913 - upsert de una release: un campo por columna
        self,
        ref: str,
        *,
        source: str,
        severity: Severity,
        recalled: bool,
        fixed_in: str | None,
        reason: str | None,
        marked_by: str,
        marked_at: datetime | None = None,
    ) -> ReleaseInfo:
        """Marca (crea o actualiza, upsert por ``(ref, source)``) una release.

        El ``ref`` debe ser un tag de Book válido (``book/<id>/vX.Y.Z``): de
        ahí se derivan ``book_id`` y ``version``.
        """
        try:
            book_id = _book_id_of(ref)
            version = SemVer.from_tag(ref)
        except (ValueError, ReleaseStoreError) as exc:
            raise ReleaseStoreError(str(exc)) from exc
        with self._session() as session:
            row = session.get(ReleaseRow, (ref, source))
            if row is None:
                row = ReleaseRow(
                    ref=ref,
                    source=source,
                    book_id=book_id,
                    version=str(version),
                    marked_by=marked_by,
                )
                session.add(row)
            row.severity = severity.value
            row.recalled = recalled
            row.fixed_in = str(SemVer.parse(fixed_in)) if fixed_in else None
            row.reason = reason
            if marked_at is not None:
                row.marked_at = marked_at
            session.add(row)
            session.commit()
            session.refresh(row)
            info = ReleaseInfo.from_row(row)
        self.record_event(
            "release.mark",
            actor=marked_by,
            source=source,
            book_id=book_id,
            version=str(version),
            detail={
                "severity": severity.value,
                "recalled": recalled,
                "fixed_in": info.fixed_in,
                "reason": reason,
            },
            at=marked_at,
        )
        return info

    def get(self, ref: str, *, source: str) -> ReleaseInfo | None:
        """Release marcada para ``(ref, source)``, o ``None`` si no hay marca."""
        with self._session() as session:
            row = session.get(ReleaseRow, (ref, source))
            return ReleaseInfo.from_row(row) if row is not None else None

    def list_for(self, book_id: str, *, source: str | None = None) -> list[ReleaseInfo]:
        """Releases marcadas de un Book, más recientes primero.

        Con ``source`` se filtra por fuente; sin ella se listan todas
        (el CLI las muestra con su columna ``source``).
        """
        with self._session() as session:
            statement = select(ReleaseRow).where(ReleaseRow.book_id == book_id)
            if source is not None:
                statement = statement.where(ReleaseRow.source == source)
            rows = session.exec(statement).all()
            infos = [ReleaseInfo.from_row(row) for row in rows]
        return sorted(
            infos, key=lambda info: SemVer.parse(info.version).precedence_key(), reverse=True
        )

    # -- auditoría (ENG-095) -------------------------------------------------------

    def record_event(  # noqa: PLR0913 - evento de auditoría: un campo por dimensión
        self,
        event_type: str,
        *,
        actor: str,
        source: str | None = None,
        book_id: str | None = None,
        version: str | None = None,
        detail: dict[str, object] | None = None,
        at: datetime | None = None,
    ) -> AuditEvent:
        """Añade un evento a la auditoría append-only (quién/cuándo/qué)."""
        with self._session() as session:
            row = AuditEventRow(
                event_type=event_type,
                actor=actor,
                source=source,
                book_id=book_id,
                version=version,
                detail=dict(detail or {}),
            )
            if at is not None:
                row.at = at
            session.add(row)
            session.commit()
            session.refresh(row)
            return AuditEvent.from_row(row)

    def audit(self, *, limit: int = 100, book_id: str | None = None) -> list[AuditEvent]:
        """Últimos eventos de auditoría (más recientes primero), filtrables por book."""
        with self._session() as session:
            statement = select(AuditEventRow)
            if book_id is not None:
                statement = statement.where(AuditEventRow.book_id == book_id)
            id_column = cast("Column[int]", AuditEventRow.id)
            statement = statement.order_by(id_column.desc()).limit(limit)
            rows = session.exec(statement).all()
        return [AuditEvent.from_row(row) for row in rows]


_REF_PARTS = 3  # book / <id> / vX.Y.Z


def _book_id_of(ref: str) -> str:
    """Extrae el id del Book de un tag ``book/<id>/vX.Y.Z``."""
    parts = ref.strip().split("/")
    if len(parts) != _REF_PARTS or parts[0] != "book" or not parts[2].startswith("v"):
        msg = f"ref inválido (se esperaba 'book/<id>/vX.Y.Z'): {ref!r}"
        raise ReleaseStoreError(msg)
    return parts[1]
