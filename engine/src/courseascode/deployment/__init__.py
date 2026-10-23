"""Deployment engine: planner y executor idempotentes; ciclo deploy/rollback (§17-§19).

División del pipeline de §17:

- ``DeploymentService`` (``service.py``): orquesta — resuelve ref, checkout,
  validación, render en dos pasadas con subida de assets (ENG-072), planner,
  executor y estado.
- ``Planner`` (``planner.py``): diff objetivo vs Moodle → ``DeploymentPlan``.
- ``Executor`` (``executor.py``): aplica el plan vía ``MoodleProvider`` y
  registra el despliegue con su ``content_hash``.
- ``compute_state`` (``state.py``): estados de §19 (incl. drift, ENG-074).
- ``ReleasePort`` (``releases.py``): puerto del registro de releases
  (severidad/recall, ENG-075); persistencia real en Fase 8.
"""

from courseascode.deployment.executor import DeploymentExecutionError, Executor
from courseascode.deployment.export import build_export, export_course
from courseascode.deployment.hashes import (
    deserialize_hashes,
    hash_html,
    hashes_of,
    serialize_hashes,
)
from courseascode.deployment.planner import Planner, RecalledVersionError
from courseascode.deployment.releases import AuditableReleasePort, NullReleasePort, ReleasePort
from courseascode.deployment.service import BookStatus, DeploymentService, DeploymentServiceError
from courseascode.deployment.state import StateInfo, compute_state

__all__ = [
    "AuditableReleasePort",
    "BookStatus",
    "DeploymentExecutionError",
    "DeploymentService",
    "DeploymentServiceError",
    "Executor",
    "NullReleasePort",
    "Planner",
    "RecalledVersionError",
    "ReleasePort",
    "StateInfo",
    "build_export",
    "compute_state",
    "deserialize_hashes",
    "export_course",
    "hash_html",
    "hashes_of",
    "serialize_hashes",
]
