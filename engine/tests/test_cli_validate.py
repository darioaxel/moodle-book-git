"""Tests del comando ``courseascode validate`` (ENG-015)."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from typer.testing import CliRunner

from courseascode.cli.main import app

runner = CliRunner()

FIXTURES = Path(__file__).parent / "fixtures" / "repos"
EXIT_USAGE = 2


def test_validate_valido_exit_0() -> None:
    result = runner.invoke(app, ["validate", str(FIXTURES / "valid")])
    assert result.exit_code == 0
    assert "Validation successful." in result.output


def test_validate_invalido_exit_1() -> None:
    result = runner.invoke(app, ["validate", str(FIXTURES / "invalid" / "07-broken-internal-link")])
    assert result.exit_code == 1
    assert "Broken link: 07-ejemplo.md" in result.output


def test_validate_ref_desde_tag(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    shutil.copytree(FIXTURES / "valid", repo)

    def git(*args: str) -> None:
        subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)

    git("init", "-q")
    git("add", "-A")
    git("-c", "user.email=test@example.com", "-c", "user.name=Test", "commit", "-qm", "v1")
    git("tag", "book/ut03-mvc/v1.0.0")

    # Rompemos el working tree tras el tag: --ref debe validar el tag, no el disco.
    (repo / "books" / "ut03-mvc" / "02-mvc.md").write_text(
        "[roto](99-inexistente.md)\n", encoding="utf-8"
    )

    result = runner.invoke(app, ["validate", str(repo), "--ref", "book/ut03-mvc/v1.0.0"])
    assert result.exit_code == 0, result.output
    assert "Validation successful." in result.output


def test_validate_ref_invalido_exit_2(tmp_path: Path) -> None:
    result = runner.invoke(app, ["validate", str(tmp_path), "--ref", "v1.0.0"])
    assert result.exit_code == EXIT_USAGE
