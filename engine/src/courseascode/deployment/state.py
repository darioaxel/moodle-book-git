"""Cálculo del ``DeploymentState`` de un Book en un curso (ENG-074, §19).

Estados (§19):

- ``NOT_DEPLOYED``: sin registro de despliegue en la tabla del plugin.
- ``UPDATE_AVAILABLE``: hay despliegue, pero la versión objetivo (la última
  disponible, cuando el caller la conoce) es distinta; la severidad viene del
  ``ReleasePort`` (ENG-075) para el badge amarillo/rojo del plugin: primero la
  de la versión objetivo (la actualización pendiente) y, si no está marcada,
  la de la versión desplegada (Fase 8: un curso que ya tiene una versión
  crítica/recalled recibe el aviso aunque no sepa de la nueva, §11).
- ``DRIFT_DETECTED``: la versión coincide (no se pide otra), pero el HTML
  actual del Book en Moodle difiere del ``content_hash`` registrado: alguien
  editó el contenido a mano (§19.1). También cubre el caso en que el Book fue
  eliminado a mano de Moodle.
- ``UP_TO_DATE``: versión e HTML coinciden con el último despliegue.
- ``ERROR``: dos casos (ENG-102): el último despliegue registrado tiene
  ``status != "success"`` (falló a mitad y quedó registrado como ``error``) o
  la lectura falló con un ``MoodleError`` inesperado (red, función del
  plugin ausente…); el ``detail`` explica el fallo y cómo recuperarse.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from courseascode.deployment.hashes import deserialize_hashes, hashes_of
from courseascode.deployment.releases import NullReleasePort, ReleasePort
from courseascode.domain.deployment import DeploymentState, Severity
from courseascode.domain.semver import SemVer
from courseascode.moodle.provider import DeployRecord, MoodleError, MoodleProvider


class StateInfo(BaseModel):
    """Estado desplegado de un Book en un curso, con contexto para la UI."""

    model_config = ConfigDict(frozen=True)

    state: DeploymentState
    severity: Severity | None = Field(
        default=None, description="Badge de UPDATE_AVAILABLE (normal | critical, §11)"
    )
    version: SemVer | None = Field(default=None, description="Versión desplegada actualmente")
    git_commit: str = ""
    detail: str = ""


def compute_state(  # noqa: PLR0913, PLR0917 - API pública del cálculo de estado (ENG-074)
    moodle: MoodleProvider,
    releases: ReleasePort | None,
    courseid: int,
    source: str,
    book_id: str,
    target_version: SemVer | None = None,
) -> StateInfo:
    """Estado del despliegue de ``(source, book_id)`` en ``courseid``.

    ``target_version`` es la versión hacia la que se podría actualizar (la
    última taggeada, si el caller la resuelve); sin ella no puede haber
    UPDATE_AVAILABLE y solo se comprueba drift/up-to-date.
    """
    port = releases or NullReleasePort()
    try:
        record = moodle.get_deploy(courseid, source, book_id)
    except MoodleError as exc:
        return StateInfo(state=DeploymentState.ERROR, detail=str(exc))
    if record is None:
        return StateInfo(state=DeploymentState.NOT_DEPLOYED)
    version = SemVer.parse(record.content_version)
    if record.status != "success":
        # ENG-102: el último deploy registrado falló a mitad; se recupera
        # relanzando el mismo deploy (el pipeline es idempotente, §17.3).
        return StateInfo(
            state=DeploymentState.ERROR,
            version=version,
            git_commit=record.git_commit,
            detail=(
                f"el último despliegue falló (status={record.status}):"
                " relanza el mismo deploy para recuperar; es idempotente"
            ),
        )
    if target_version is not None and target_version != version:
        severity = port.severity_of(source, book_id, target_version)
        if severity is None:
            # §11: quien ya tiene una versión marcada (p. ej. critical+recalled
            # pendiente de hotfix) recibe el aviso aunque la nueva no esté marcada.
            severity = port.severity_of(source, book_id, version)
        return StateInfo(
            state=DeploymentState.UPDATE_AVAILABLE,
            severity=severity,
            version=version,
            git_commit=record.git_commit,
            detail=f"disponible: {target_version}",
        )
    return _state_for_same_version(moodle, record, version)


def _state_for_same_version(
    moodle: MoodleProvider, record: DeployRecord, version: SemVer
) -> StateInfo:
    """UP_TO_DATE vs DRIFT_DETECTED cuando la versión coincide con la desplegada."""
    try:
        remote = moodle.get_book(record.bookid)
    except MoodleError as exc:
        return StateInfo(
            state=DeploymentState.ERROR,
            version=version,
            git_commit=record.git_commit,
            detail=str(exc),
        )
    if remote is None:
        return StateInfo(
            state=DeploymentState.DRIFT_DETECTED,
            version=version,
            git_commit=record.git_commit,
            detail="el Book fue eliminado manualmente de Moodle",
        )
    stored = _stored_hashes(record.content_hash)
    current = hashes_of((stable_id, chapter.html) for stable_id, chapter in remote.chapters.items())
    if stored != current:
        drifted = sorted(set(stored) ^ set(current) | _diff_keys(stored, current))
        return StateInfo(
            state=DeploymentState.DRIFT_DETECTED,
            version=version,
            git_commit=record.git_commit,
            detail="contenido modificado manualmente en Moodle: " + ", ".join(drifted),
        )
    return StateInfo(
        state=DeploymentState.UP_TO_DATE, version=version, git_commit=record.git_commit
    )


def _stored_hashes(raw: str) -> dict[str, str]:
    try:
        return deserialize_hashes(raw)
    except ValueError:
        return {}


def _diff_keys(a: dict[str, str], b: dict[str, str]) -> set[str]:
    return {key for key in a.keys() & b.keys() if a[key] != b[key]}
