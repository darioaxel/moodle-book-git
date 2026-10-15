"""Endpoints REST de despliegue (ENG-079), montados en la app de ``web/app.py``.

El plugin Moodle (y cualquier cliente HTTP) consume aquí el mismo pipeline
que la CLI (principio 5: un solo código de publicación, §17):

- ``POST /deploy``: pipeline completo (plan + ejecución). Al ser no
  interactivo, las eliminaciones requieren ``confirmed_deletions: true``
  explícito (§17.2); si no, se omiten y quedan avisadas en el resultado.
- ``POST /deployment/plan``: plan sin ejecutar (previsualización, §17.1).
- ``GET /deployment/status``: estado de §19 de un Book en un curso.
- ``GET /deployment/where``: consulta inversa — cursos con una versión dada
  como despliegue actual (hotfixes, ENG-094). Resuelve vía la 9ª función
  asumida del plugin (``where_deployed``): el engine no puede buscar en
  global sin ella.

La app se construye con ``create_deployment_router(deps)``; si falta el
provider Git o el de Moodle, los endpoints responden 503 con un JSON claro
(el router se monta siempre para que el contrato de rutas sea estable).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from courseascode.deployment.planner import RecalledVersionError
from courseascode.deployment.releases import ReleasePort
from courseascode.deployment.service import DeploymentService, DeploymentServiceError
from courseascode.git.provider import GitProvider, GitProviderError
from courseascode.moodle.provider import MoodleError, MoodleProvider

SOURCE_RE = re.compile(r"^[a-z0-9_-]+$")


@dataclass(frozen=True)
class DeploymentApiDeps:
    """Dependencias de los endpoints de despliegue (inyectadas desde ``create_app``)."""

    git: GitProvider | None
    moodle: MoodleProvider | None
    releases: ReleasePort | None = None
    source: str = "dwes"


class DeployRequest(BaseModel):
    """Cuerpo de ``POST /deploy`` y ``POST /deployment/plan``."""

    course_id: int = Field(gt=0)
    source: str = Field(default="dwes", min_length=1)
    book_id: str = Field(min_length=1)
    ref: str | None = Field(default=None, description="Tag, rama o commit (alternativa a version)")
    version: str | None = Field(default=None, description="SemVer a desplegar (alternativa a ref)")
    force: bool = Field(default=False, description="Permite desplegar versiones RECALLED (§18)")
    confirmed_deletions: bool = Field(
        default=False, description="Autoriza las eliminaciones de capítulos (§17.2)"
    )


def create_deployment_router(deps: DeploymentApiDeps) -> APIRouter:
    """Router con los endpoints de despliegue sobre las dependencias dadas."""
    router = APIRouter()

    def service() -> DeploymentService:
        if deps.git is None or deps.moodle is None:
            raise HTTPException(
                status_code=503,
                detail="despliegue no disponible: faltan el provider Git o la configuración Moodle",
            )
        return DeploymentService(deps.git, deps.moodle, deps.releases, source=deps.source)

    @router.post("/deploy")
    def deploy(request: DeployRequest) -> dict[str, object]:
        """Pipeline completo de §17 (plan + ejecución idempotente)."""
        _check_source(request.source)
        try:
            result = service().deploy(
                request.course_id,
                request.book_id,
                version=request.version,
                ref=request.ref,
                confirmed_deletions=request.confirmed_deletions,
                force=request.force,
                deployed_by="api",
            )
        except RecalledVersionError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except (DeploymentServiceError, GitProviderError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except MoodleError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        return result.model_dump(mode="json")

    @router.post("/deployment/plan")
    def plan(request: DeployRequest) -> dict[str, object]:
        """Genera el plan sin ejecutarlo (formato §17.1 vía ``summary()``)."""
        _check_source(request.source)
        try:
            deployment_plan = service().plan(
                request.course_id,
                request.book_id,
                version=request.version,
                ref=request.ref,
                force=request.force,
            )
        except RecalledVersionError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except (DeploymentServiceError, GitProviderError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except MoodleError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        return deployment_plan.model_dump(mode="json")

    @router.get("/deployment/status")
    def status(
        course_id: int = Query(gt=0),
        source: str = Query(default="dwes"),
        book_id: str = Query(min_length=1),
    ) -> dict[str, object]:
        """Estado del despliegue (§19): NOT_DEPLOYED, UP_TO_DATE, DRIFT…"""
        _check_source(source)
        try:
            info = service().state(course_id, book_id, source=source)
        except MoodleError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        return info.model_dump(mode="json")

    @router.get("/deployment/where")
    def where(
        source: str = Query(min_length=1),
        book: str = Query(min_length=1),
        version: str = Query(min_length=1),
    ) -> dict[str, object]:
        """Cursos cuyo despliegue actual de ``(source, book)`` es ``version``."""
        _check_source(source)
        if deps.moodle is None:
            raise HTTPException(status_code=503, detail="Moodle no configurado")
        try:
            courses = deps.moodle.where_deployed(source, book, version)
        except MoodleError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        return {"courses": courses}

    return router


def _check_source(source: str) -> None:
    if not SOURCE_RE.match(source):
        raise HTTPException(status_code=404, detail=f"fuente inválida: {source!r}")
