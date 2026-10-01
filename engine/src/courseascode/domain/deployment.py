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
    """Acción atómica del plan. Las eliminaciones requieren confirmación (§17.2)."""

    model_config = ConfigDict(frozen=True)

    kind: ActionKind
    target: str = Field(min_length=1, description="book | chapter | asset")
    stable_id: str | None = None
    title: str = ""
    requires_confirmation: bool = False


class DeploymentPlan(BaseModel):
    """Diff entre el estado actual en Moodle y el objetivo (§17.1)."""

    model_config = ConfigDict(frozen=True)

    course_id: int
    content: ContentId
    current_version: SemVer | None
    target_version: SemVer
    actions: tuple[DeploymentAction, ...] = ()

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
            "",
            "Moodle actions:",
        ]
        for action in self.actions:
            marker = {ActionKind.CREATE: "+", ActionKind.UPDATE: "~", ActionKind.DELETE: "-"}
            label = action.title or action.stable_id or action.target
            if action.kind is ActionKind.UPLOAD:
                lines.append(f"  UPLOAD {label}")
            else:
                lines.append(f"  {action.kind.value} {action.target} {marker[action.kind]} {label}")
        return "\n".join(lines)


class DeploymentResult(BaseModel):
    """Resultado de ejecutar un plan."""

    model_config = ConfigDict(frozen=True)

    success: bool
    actions_applied: tuple[DeploymentAction, ...] = ()
    duration_seconds: float = 0.0
    message: str = ""


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
