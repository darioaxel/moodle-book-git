"""Endpoints de releases y auditoría (ENG-094/ENG-095).

- ``GET /releases/affected``: dado ``(source, book, version)``, los cursos con
  esa versión como despliegue actual (consulta inversa §11.1 paso 5) con
  detalle para la notificación dirigida: ``deployed_by`` es el mejor proxy de
  "profesor responsable" disponible sin consultar usuarios Moodle, y la
  severidad/fixed_in/reason salen de la release marcada. **El envío de la
  notificación es del plugin 🔌**: el servicio solo calcula.
- ``GET /audit``: lectura de la auditoría (ENG-095). Endpoint **admin**: exige
  el header ``X-CourseAsCode-Admin-Token`` con el token configurado
  (``COURSEASCODE_ADMIN_TOKEN``); sin token configurado o sin store, 503.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from fastapi import APIRouter, Header, HTTPException, Query

from courseascode.domain.semver import SemVer, SemVerError
from courseascode.moodle.provider import MoodleError, MoodleProvider
from courseascode.releases.store import ReleaseStore


@dataclass(frozen=True)
class ReleasesApiDeps:
    """Dependencias de los endpoints de releases/auditoría (inyectadas)."""

    moodle: MoodleProvider | None
    store: ReleaseStore | None
    admin_token: str | None = None


def create_releases_router(deps: ReleasesApiDeps) -> APIRouter:
    """Router de ``/releases/affected`` y ``/audit`` sobre las dependencias dadas."""
    router = APIRouter()

    @router.get("/releases/affected")
    def affected(
        source: Annotated[str, Query(min_length=1)],
        book: Annotated[str, Query(min_length=1)],
        version: Annotated[str, Query(min_length=1)],
    ) -> dict[str, object]:
        if deps.moodle is None:
            raise HTTPException(status_code=503, detail="Moodle no configurado")
        try:
            semver = str(SemVer.parse(version))
        except SemVerError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        ref = f"book/{book}/v{semver}"
        release = deps.store.get(ref, source=source) if deps.store is not None else None
        try:
            courses = deps.moodle.where_deployed(source, book, semver)
            items = []
            for courseid in courses:
                record = deps.moodle.get_deploy(courseid, source, book)
                items.append(
                    {
                        "course_id": courseid,
                        "deployed_version": record.content_version if record else semver,
                        "deployed_by": record.deployed_by if record else None,
                        "deployed_at": record.deployed_at.isoformat() if record else None,
                        "severity": release.severity if release else None,
                        "recalled": release.recalled if release else None,
                        "fixed_in": release.fixed_in if release else None,
                        "reason": release.reason if release else None,
                    }
                )
        except MoodleError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        return {
            "source": source,
            "book": book,
            "version": semver,
            "marked": release is not None,
            "affected": items,
        }

    @router.get("/audit")
    def audit(
        limit: Annotated[int, Query(ge=1, le=1000)] = 100,
        book_id: Annotated[str | None, Query(min_length=1)] = None,
        admin_token: Annotated[str | None, Header(alias="X-CourseAsCode-Admin-Token")] = None,
    ) -> dict[str, object]:
        if deps.store is None or not deps.admin_token:
            raise HTTPException(
                status_code=503,
                detail=(
                    "auditoría no disponible: configura COURSEASCODE_DB y "
                    "COURSEASCODE_ADMIN_TOKEN en el servicio"
                ),
            )
        if admin_token is None or admin_token != deps.admin_token:
            raise HTTPException(status_code=401, detail="token de administrador inválido o ausente")
        events = deps.store.audit(limit=limit, book_id=book_id)
        return {"events": [event.model_dump(mode="json") for event in events]}

    return router
