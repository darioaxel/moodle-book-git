"""Tests del parser y el validador (ENG-012-016)."""

from __future__ import annotations

from pathlib import Path

import pytest

from courseascode.manifests import ManifestParser, Validator
from courseascode.manifests.errors import ManifestError

FIXTURES = Path(__file__).parent / "fixtures" / "repos"

EXPECTED_CHAPTERS = 5
EXPECTED_ASSETS = 2


class TestManifestParser:
    def test_parse_course_valido(self) -> None:
        course = ManifestParser(FIXTURES / "valid").parse_course()
        assert course.id == "dwes"
        assert [b.id for b in course.books] == ["ut03-mvc"]

    def test_parse_book_valido(self) -> None:
        parser = ManifestParser(FIXTURES / "valid")
        book = parser.parse_book(FIXTURES / "valid" / "books" / "ut03-mvc")
        assert book.id == "ut03-mvc"
        assert len(book.chapters) == EXPECTED_CHAPTERS
        assert book.to_domain().numbering.value == "numbers"

    def test_yaml_invalido_localiza_linea(self) -> None:
        parser = ManifestParser(FIXTURES / "invalid" / "01-course-yaml-invalid")
        with pytest.raises(ManifestError) as excinfo:
            parser.parse_course()
        issue = excinfo.value.issues[0]
        assert issue.file is not None and issue.file.name == "course.yml"
        assert issue.line is not None

    def test_campo_invalido_reporta_campo(self) -> None:
        parser = ManifestParser(FIXTURES / "invalid" / "10-invalid-numbering")
        with pytest.raises(ManifestError) as excinfo:
            parser.parse_book(FIXTURES / "invalid" / "10-invalid-numbering" / "books" / "ut03-mvc")
        assert any("numbering" in issue.message for issue in excinfo.value.issues)


class TestValidator:
    def test_repo_valido_pasa(self) -> None:
        report = Validator().validate(FIXTURES / "valid")
        assert report.ok
        rendered = report.render()
        assert "✓ course.yml" in rendered
        assert "✓ 5 chapters" in rendered
        assert f"✓ {EXPECTED_ASSETS} assets" in rendered
        assert rendered.rstrip().endswith("Validation successful.")

    @pytest.mark.parametrize(
        ("case", "expected"),
        [
            ("01-course-yaml-invalid", "YAML"),
            ("02-book-yaml-invalid", "YAML"),
            ("03-duplicate-chapter-ids", "duplicado"),
            ("04-duplicate-book-ids", "duplicado"),
            ("05-missing-chapter-file", "no encontrado"),
            ("06-missing-asset", "asset no encontrado"),
            ("07-broken-internal-link", "Broken link: 07-ejemplo.md"),
            ("08-unclosed-container", "sin cerrar"),
            ("09-missing-catalog-metadata", "summary"),
            ("10-invalid-numbering", "numbering"),
        ],
    )
    def test_repo_invalido_falla_con_error_especifico(self, case: str, expected: str) -> None:
        report = Validator().validate(FIXTURES / "invalid" / case)
        assert not report.ok
        assert any(expected in issue.message for issue in report.issues), (
            f"{case}: ningún issue menciona {expected!r}: {[i.message for i in report.issues]}"
        )
        assert "Validation failed." in report.render()

    def test_issue_localiza_archivo_y_linea(self) -> None:
        report = Validator().validate(FIXTURES / "invalid" / "07-broken-internal-link")
        issue = next(i for i in report.issues if "Broken link" in i.message)
        assert issue.file is not None and issue.file.name == "01-intro.md"
        assert issue.line is not None

    def test_curso_sin_manifest(self, tmp_path: Path) -> None:
        report = Validator().validate(tmp_path)
        assert not report.ok
        assert any("no encontrado" in i.message for i in report.issues)
