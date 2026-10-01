"""Validación completa de un repo de contenidos (§20 de la spec).

Reglas: YAML válido · IDs únicos (books y capítulos) · archivos de capítulos
existentes · assets referenciados existentes · enlaces internos resolubles ·
Markdown válido (contenedores cerrados) · estructura del Book · metadatos de
catálogo presentes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from courseascode.manifests.errors import ManifestError, ValidationIssue
from courseascode.manifests.markdown_scanner import scan_markdown
from courseascode.manifests.models import BookManifest, BookRef
from courseascode.manifests.parser import ManifestParser

LABEL_CHAPTERS = "chapters"
LABEL_ASSETS = "assets"
LABEL_LINKS = "internal links"
LABEL_MARKDOWN = "Markdown"
LABEL_METADATA = "catalog metadata"

_EXTERNAL_SCHEMES = ("http://", "https://", "mailto:", "tel:", "data:")


@dataclass(frozen=True)
class CheckResult:
    """Una línea ✓/✗ del resumen de validación."""

    label: str
    ok: bool


@dataclass
class ValidationReport:
    """Resultado de validar un repo: checks resumidos + issues localizados."""

    root: Path
    checks: list[CheckResult] = field(default_factory=list)
    issues: list[ValidationIssue] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.issues

    def render(self) -> str:
        lines = [f"{'✓' if check.ok else '✗'} {check.label}" for check in self.checks]
        if self.issues:
            lines.append("")
            lines.extend(issue.render(self.root) for issue in self.issues)
        lines.append("")
        if self.ok:
            lines.append("Validation successful.")
        else:
            lines.append(f"Validation failed. {len(self.issues)} error(s).")
        return "\n".join(lines)


class Validator:
    """Valida un repo de contenidos y genera un ``ValidationReport``."""

    def __init__(self) -> None:
        self._issues: list[ValidationIssue] = []
        self._checks: list[CheckResult] = []
        self._root = Path.cwd()

    def validate(self, root: Path) -> ValidationReport:
        self._root = root
        self._issues = []
        self._checks = []
        parser = ManifestParser(root)

        try:
            course = parser.parse_course()
        except ManifestError as exc:
            self._issues.extend(exc.issues)
            self._checks.append(CheckResult("course.yml", ok=False))
            return self._report()
        self._checks.append(CheckResult("course.yml", ok=True))

        self._check_unique_book_ids(course.books)

        total_chapters = 0
        total_assets = 0
        for book_ref in course.books:
            book_dir = root / book_ref.path
            book_file = book_dir / "book.yml"
            try:
                book = parser.parse_book(book_dir)
            except ManifestError as exc:
                self._issues.extend(exc.issues)
                self._checks.append(CheckResult(self._rel(book_file), ok=False))
                continue
            self._checks.append(CheckResult(self._rel(book_file), ok=True))
            self._check_unique_chapter_ids(book, book_file)
            self._check_catalog_metadata(book, book_file)
            total_chapters += len(book.chapters)
            total_assets += self._check_chapters(book, book_dir)

        self._aggregate(LABEL_CHAPTERS, f"{total_chapters} chapters")
        self._aggregate(LABEL_ASSETS, f"{total_assets} assets")
        self._aggregate(LABEL_LINKS, LABEL_LINKS)
        self._aggregate(LABEL_MARKDOWN, LABEL_MARKDOWN)
        self._aggregate(LABEL_METADATA, LABEL_METADATA)
        return self._report()

    # -- reglas ---------------------------------------------------------------

    def _check_unique_book_ids(self, books: tuple[BookRef, ...]) -> None:
        seen: set[str] = set()
        for ref in books:
            if ref.id in seen:
                self._issue("course.yml", f"ID de Book duplicado: {ref.id}")
            seen.add(ref.id)

    def _check_unique_chapter_ids(self, book: BookManifest, book_file: Path) -> None:
        label = self._rel(book_file)
        seen: set[str] = set()
        for chapter in book.chapters:
            if chapter.id in seen:
                self._issue(label, f"ID de capítulo duplicado: {chapter.id}", file=book_file)
            seen.add(chapter.id)

    def _check_catalog_metadata(self, book: BookManifest, book_file: Path) -> None:
        if not book.summary.strip():
            self._issue(LABEL_METADATA, "falta el campo obligatorio 'summary'", file=book_file)
        if not book.tags:
            self._issue(LABEL_METADATA, "falta el campo obligatorio 'tags'", file=book_file)
        if not book.audience.strip():
            self._issue(LABEL_METADATA, "falta el campo obligatorio 'audience'", file=book_file)

    def _check_chapters(self, book: BookManifest, book_dir: Path) -> int:
        """Valida archivos de capítulos, assets y enlaces; devuelve nº de assets."""
        chapter_files = {self._normalize(ch.file) for ch in book.chapters}
        assets: set[str] = set()

        if book.cover is not None:
            self._check_asset(book_dir / book.cover, book_dir, assets)

        for chapter in book.chapters:
            chapter_path = book_dir / chapter.file
            if not chapter_path.is_file():
                self._issue(
                    LABEL_CHAPTERS,
                    f"archivo de capítulo no encontrado: {chapter.file}",
                    file=book_dir / "book.yml",
                )
                continue
            try:
                text = chapter_path.read_text(encoding="utf-8")
            except OSError as exc:
                self._issue(LABEL_MARKDOWN, f"no se puede leer: {exc}", file=chapter_path)
                continue
            references, container_issues = scan_markdown(text)
            for container in container_issues:
                self._issue(
                    LABEL_MARKDOWN,
                    "contenedor de admonition sin cerrar (se esperaba ':::')",
                    file=chapter_path,
                    line=container.line,
                )
            for ref in references:
                if self._is_external(ref.target):
                    continue
                if ref.kind == "image":
                    if self._check_asset(chapter_path.parent / ref.target, book_dir, assets):
                        pass  # contado
                    else:
                        self._issue(
                            LABEL_ASSETS,
                            f"asset no encontrado: {ref.target}",
                            file=chapter_path,
                            line=ref.line,
                        )
                else:
                    target = self._strip_fragment(ref.target)
                    if target.endswith(".md") and self._normalize(target) not in chapter_files:
                        self._issue(
                            LABEL_LINKS,
                            f"Broken link: {ref.target}",
                            file=chapter_path,
                            line=ref.line,
                        )
        return len(assets)

    def _check_asset(self, path: Path, book_dir: Path, assets: set[str]) -> bool:
        if path.is_file():
            try:
                assets.add(str(path.relative_to(book_dir)))
            except ValueError:
                assets.add(str(path))
            return True
        return False

    # -- utilidades -------------------------------------------------------------

    def _aggregate(self, category: str, label: str) -> None:
        ok = not any(issue.category == category for issue in self._issues)
        self._checks.append(CheckResult(label, ok))

    def _issue(
        self, category: str, message: str, file: Path | None = None, line: int | None = None
    ) -> None:
        self._issues.append(
            ValidationIssue(category=category, message=message, file=file, line=line)
        )

    def _report(self) -> ValidationReport:
        return ValidationReport(root=self._root, checks=self._checks, issues=self._issues)

    def _rel(self, path: Path) -> str:
        try:
            return str(path.relative_to(self._root))
        except ValueError:
            return str(path)

    @staticmethod
    def _normalize(target: str) -> str:
        return str(PurePosixPath(target))

    @staticmethod
    def _strip_fragment(target: str) -> str:
        return target.split("#", 1)[0].split("?", 1)[0]

    @staticmethod
    def _is_external(target: str) -> bool:
        if target.startswith("#") or target.startswith("//"):
            return True
        return any(target.startswith(scheme) for scheme in _EXTERNAL_SCHEMES)
