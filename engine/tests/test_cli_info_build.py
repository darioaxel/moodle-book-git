"""Tests de los comandos ``courseascode info`` y ``courseascode build`` (ENG-054)."""

from __future__ import annotations

import re
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from courseascode.cli.main import app

runner = CliRunner()

FIXTURES = Path(__file__).parent / "fixtures" / "repos"
VALID_REPO = FIXTURES / "valid"

EXIT_USAGE = 2
UT03_CHAPTERS = 6  # 5 iniciales + observer (tag v1.1.0, presente en main)
COMMIT_RE = re.compile(r"Git commit:  [0-9a-f]{7}")


def test_info_muestra_los_campos_de_la_spec(
    git_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(git_repo)
    result = runner.invoke(app, ["info", "ut03-mvc"])
    assert result.exit_code == 0, result.output
    out = result.output
    # Formato de §29 (columnas alineadas).
    assert "ID:          @dwes/ut03-mvc" in out
    assert "Title:       MVC y patrones de diseño" in out
    assert "Type:        book" in out
    assert "Chapters:    6" in out  # working tree de main: 5 + observer
    assert "Assets:      2" in out  # mvc.svg + ejemplo.png
    assert COMMIT_RE.search(out)
    assert "Tags:        v1.0.0, v1.1.0, v1.2.0" in out


def test_info_acepta_ruta_de_directorio(git_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(git_repo)
    result = runner.invoke(app, ["info", "books/ut04-dao"])
    assert result.exit_code == 0, result.output
    assert "ID:          @dwes/ut04-dao" in result.output
    assert "Chapters:    1" in result.output
    assert "Tags:        v1.0.0" in result.output


def test_info_sin_repo_git_muestra_working_tree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    loose = tmp_path / "suelto"
    shutil.copytree(VALID_REPO, loose)
    monkeypatch.chdir(loose)
    result = runner.invoke(app, ["info", "ut03-mvc"])
    assert result.exit_code == 0, result.output
    assert "ID:          @dwes/ut03-mvc" in result.output
    assert "Chapters:    5" in result.output
    assert "Git commit:  -" in result.output
    assert "Tags:        -" in result.output


def test_info_book_desconocido_exit_2(git_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(git_repo)
    result = runner.invoke(app, ["info", "ut99-desconocido"])
    assert result.exit_code == EXIT_USAGE
    assert "no está en course.yml" in result.output


def test_build_genera_html_con_tema_y_assets(
    git_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(git_repo)
    result = runner.invoke(app, ["build", "ut03-mvc"])
    assert result.exit_code == 0, result.output
    out_dir = git_repo / "build" / "ut03-mvc"
    assert "Build generado en" in result.output
    assert str(out_dir) in result.output

    # Índice + una página por capítulo, con el tema embebido.
    index = (out_dir / "index.html").read_text(encoding="utf-8")
    assert "MVC y patrones de diseño" in index
    assert "--cc-text" in index  # CSS del tema
    assert 'href="mvc.html"' in index  # TOC con enlaces relativos
    page = (out_dir / "mvc.html").read_text(encoding="utf-8")
    assert "<h1>MVC</h1>" in page
    assert 'src="assets/mvc.svg"' in page  # asset referenciado con ruta relativa
    assert len(list(out_dir.glob("*.html"))) == 1 + UT03_CHAPTERS  # índice + capítulos

    # Assets referenciados copiados a build/<id>/assets/.
    assert (out_dir / "assets" / "mvc.svg").is_file()
    assert (out_dir / "assets" / "ejemplo.png").is_file()
    assert (out_dir / "assets" / "mvc.svg").read_bytes() == (
        VALID_REPO / "books" / "ut03-mvc" / "assets" / "mvc.svg"
    ).read_bytes()


def test_build_libro_pequeno(git_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(git_repo)
    result = runner.invoke(app, ["build", "ut04-dao"])
    assert result.exit_code == 0, result.output
    out_dir = git_repo / "build" / "ut04-dao"
    assert (out_dir / "index.html").is_file()
    page = (out_dir / "dao.html").read_text(encoding="utf-8")
    assert "<h1>DAO</h1>" in page
    assert "1 capítulos, 0 assets" in result.output


def test_build_book_desconocido_exit_2(git_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(git_repo)
    result = runner.invoke(app, ["build", "ut99-desconocido"])
    assert result.exit_code == EXIT_USAGE
    assert "no está en course.yml" in result.output
