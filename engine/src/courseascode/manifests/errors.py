"""Errores e issues de validación con localización (archivo, línea, campo)."""

from __future__ import annotations

from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ValidationIssue:
    """Un problema encontrado durante la validación."""

    category: str
    message: str
    file: Path | None = None
    line: int | None = None

    def render(self, root: Path | None = None) -> str:
        location = ""
        if self.file is not None:
            path = self.file
            if root is not None:
                with suppress(ValueError):
                    path = path.relative_to(root)
            location = str(path)
            if self.line is not None:
                location += f":{self.line}"
            location += " — "
        return f"  ✗ {location}{self.message}"


class ManifestError(Exception):
    """Fallo de carga o parseo de un manifest, con issues localizados."""

    def __init__(self, issues: list[ValidationIssue]) -> None:
        self.issues = issues
        super().__init__(issues[0].message if issues else "error de manifest")
