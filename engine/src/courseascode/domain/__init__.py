"""Modelos de dominio puros (sin dependencias de Git, Moodle ni API)."""

from courseascode.domain.content import Book, Chapter, Course
from courseascode.domain.deployment import (
    ActionKind,
    DeploymentAction,
    DeploymentPlan,
    DeploymentResult,
    DeploymentState,
    Severity,
)
from courseascode.domain.identity import ContentId, GitRef, RefKind
from courseascode.domain.semver import SemVer

__all__ = [
    "ActionKind",
    "Book",
    "Chapter",
    "ContentId",
    "Course",
    "DeploymentAction",
    "DeploymentPlan",
    "DeploymentResult",
    "DeploymentState",
    "GitRef",
    "RefKind",
    "SemVer",
    "Severity",
]
