"""Carga y parseo de manifests con errores localizados (ENG-012)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, TypeVar

import yaml
from pydantic import ValidationError

from courseascode.manifests.errors import ManifestError, ValidationIssue
from courseascode.manifests.models import BookManifest, CourseManifest

CATEGORY_COURSE = "course.yml"
CATEGORY_BOOK = "book.yml"

_M = TypeVar("_M", CourseManifest, BookManifest)


class ManifestParser:
    """Parsea ``course.yml`` y los ``book.yml`` de un repo de contenidos."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def parse_course(self) -> CourseManifest:
        """Carga ``course.yml`` de la raíz del repo."""
        return self._parse(CourseManifest, self.root / "course.yml")

    def parse_book(self, book_dir: Path) -> BookManifest:
        """Carga ``book.yml`` de un directorio de Book."""
        return self._parse(BookManifest, book_dir / "book.yml")

    def _parse(self, model: type[_M], file: Path) -> _M:
        category = CATEGORY_COURSE if file.name == "course.yml" else CATEGORY_BOOK
        data = self._load_yaml(file, category)
        try:
            return model.model_validate(data)
        except ValidationError as exc:
            issues = [
                ValidationIssue(
                    category=category,
                    message=f"{'.'.join(str(p) for p in error['loc'])}: {error['msg']}",
                    file=file,
                )
                for error in exc.errors()
            ]
            raise ManifestError(issues) from exc

    def _load_yaml(self, file: Path, category: str) -> Any:
        if not file.is_file():
            msg = "archivo no encontrado"
            raise ManifestError([ValidationIssue(category=category, message=msg, file=file)])
        try:
            text = file.read_text(encoding="utf-8")
        except OSError as exc:
            raise ManifestError(
                [ValidationIssue(category=category, message=f"no se puede leer: {exc}", file=file)]
            ) from exc
        try:
            data = yaml.safe_load(text)
        except yaml.MarkedYAMLError as exc:
            line = exc.problem_mark.line + 1 if exc.problem_mark is not None else None
            message = f"YAML inválido: {exc.problem or exc}"
            raise ManifestError(
                [ValidationIssue(category=category, message=message, file=file, line=line)]
            ) from exc
        except yaml.YAMLError as exc:
            raise ManifestError(
                [ValidationIssue(category=category, message=f"YAML inválido: {exc}", file=file)]
            ) from exc
        if data is None:
            return {}
        if not isinstance(data, dict):
            msg = "el manifest debe ser un mapa YAML (clave: valor)"
            raise ManifestError([ValidationIssue(category=category, message=msg, file=file)])
        return data
