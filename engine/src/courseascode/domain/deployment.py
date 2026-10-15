"""Plan y resultado de despliegue; estados de despliegue (§17, §19 de la spec)."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from courseascode.domain.identity import ContentId
from courseascode.domain.semver import SemVer


class ActionKind(Enum):
    CREATE = "CREATE"
    UPDATE = "UPDATE"
    DELETE = "DELETE"
    UPLOAD = "UPLOAD"


class DeploymentAction(BaseModel):
    """Acción atómica del plan. Las eliminaciones requieren confirmación (§17.2).

    Campos por tipo de acción:

    - ``book``: ``title`` (nombre del Book), ``html`` (intro renderizada) y
      ``numbering`` (valor del enum ``Numbering``).
    - ``chapter``: ``stable_id``, ``title``, ``html`` (HTML final, con las URLs
      de assets ya resueltas en la segunda pasada, ENG-072) y ``position``
      (1-based, orden del manifest).
    - ``asset`` (UPLOAD): ``asset_path`` (ruta relativa al Book) y
      ``asset_data`` (bytes, solo si el plan se construye a mano; el pipeline
      real sube los assets *antes* de planificar, ENG-072, y esta acción queda
      como registro documental de la subida).
    """

    model_config = ConfigDict(frozen=True)

    kind: ActionKind
    target: str = Field(min_length=1, description="book | chapter | asset")
    stable_id: str | None = None
    title: str = ""
    html: str = ""
    position: int = 0
    numbering: str = ""
    asset_path: str = ""
    asset_data: bytes = b""
    requires_confirmation: bool = False


class DeploymentPlan(BaseModel):
    """Diff entre el estado actual en Moodle y el objetivo (§17.1)."""

    model_config = ConfigDict(frozen=True)

    course_id: int
    content: ContentId
    current_version: SemVer | None
    target_version: SemVer
    actions: tuple[DeploymentAction, ...] = ()
    git_ref: str = Field(default="", description="Ref Git desplegado (tag, rama o commit)")
    git_commit: str = Field(default="", description="SHA completo del commit desplegado")
    changes: tuple[str, ...] = Field(
        default=(),
        description="Cambios de contenido (formato §17.1: '+ 05-controller.md', '~ 02-mvc.md')",
    )
    warnings: tuple[str, ...] = Field(
        default=(),
        description="Avisos del plan (p. ej. despliegue forzado de versión RECALLED, ENG-075)",
    )

    @property
    def has_deletions(self) -> bool:
        return any(a.kind is ActionKind.DELETE for a in self.actions)

    @property
    def requires_confirmation(self) -> bool:
        return self.has_deletions

    def summary(self) -> str:
        """Resumen legible del plan (formato §17.1)."""
        lines = [
            "Deployment plan",
            "",
            f"Course:  {self.course_id}",
            f"Book:    {self.content}",
            f"Current: {self.current_version or '—'}",
            f"Target:  {self.target_version}",
        ]
        if self.changes:
            lines.extend(["", "Changes:"])
            lines.extend(f"  {change}" for change in self.changes)
        lines.extend(["", "Moodle actions:"])
        for action in self.actions:
            marker = {ActionKind.CREATE: "+", ActionKind.UPDATE: "~", ActionKind.DELETE: "-"}
            label = action.title or action.stable_id or action.target
            if action.kind is ActionKind.UPLOAD:
                lines.append(f"  UPLOAD {action.asset_path or label}")
            else:
                lines.append(f"  {action.kind.value} {action.target} {marker[action.kind]} {label}")
        deletions = [a for a in self.actions if a.kind is ActionKind.DELETE]
        if deletions:
            lines.extend(
                [
                    "",
                    f"⚠ Este despliegue eliminará {len(deletions)} capítulo(s) del Book Moodle:",
                ]
            )
            lines.extend(f"  - {a.stable_id}" for a in deletions)
        if self.warnings:
            lines.extend(["", "Warnings:"])
            lines.extend(f"  ⚠ {warning}" for warning in self.warnings)
        return "\n".join(lines)


class DeploymentResult(BaseModel):
    """Resultado de ejecutar un plan."""

    model_config = ConfigDict(frozen=True)

    success: bool
    actions_applied: tuple[DeploymentAction, ...] = ()
    duration_seconds: float = 0.0
    message: str = ""
    version: str = Field(default="", description="Versión desplegada (SemVer)")
    commit: str = Field(default="", description="SHA del commit desplegado")
    warnings: tuple[str, ...] = Field(
        default=(),
        description="Avisos de la ejecución (recalls forzados, eliminaciones omitidas…)",
    )


class Severity(Enum):
    """Severidad de una actualización disponible (§11)."""

    NORMAL = "normal"
    CRITICAL = "critical"


class DeploymentState(Enum):
    """Estado del despliegue de un Book en un curso (§19)."""

    NOT_DEPLOYED = "NOT_DEPLOYED"
    UP_TO_DATE = "UP_TO_DATE"
    UPDATE_AVAILABLE = "UPDATE_AVAILABLE"
    DRIFT_DETECTED = "DRIFT_DETECTED"
    DEPLOYING = "DEPLOYING"
    ERROR = "ERROR"
