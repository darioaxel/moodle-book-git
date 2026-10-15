"""Smoke tests de los comandos ``courseascode deploy`` y ``status`` (ENG-076/078).

El cliente Moodle se inyecta mockeando ``_moodle_from_env`` (mismo patrón que
los tests CLI existentes): ningún test toca la red.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from courseascode.cli.main import app
from courseascode.moodle import FakeMoodleProvider

runner = CliRunner()

COURSE = "2026"
BOOK = "@dwes/ut03-mvc"
EXIT_OK = 0
EXIT_USAGE = 2


@pytest.fixture()
def fake() -> FakeMoodleProvider:
    return FakeMoodleProvider(course_ids=(int(COURSE),))


@pytest.fixture(autouse=True)
def _moodle_falso(monkeypatch: pytest.MonkeyPatch, fake: FakeMoodleProvider) -> None:
    monkeypatch.setattr("courseascode.cli.main._moodle_from_env", lambda: fake)


def test_deploy_yes_ejecuta_el_pipeline(
    git_repo: Path, fake: FakeMoodleProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(git_repo)

    result = runner.invoke(
        app, ["deploy", "--course", COURSE, "--book", BOOK, "--version", "1.0.0", "--yes"]
    )

    assert result.exit_code == EXIT_OK, result.output
    assert "Deployment plan" in result.output
    assert "CREATE chapter" in result.output
    assert "UPLOAD assets/mvc.svg" in result.output
    assert "Deployed @dwes/ut03-mvc v1.0.0" in result.output
    record = fake.get_deploy(int(COURSE), "dwes", "ut03-mvc")
    assert record is not None
    assert record.content_version == "1.0.0"


def test_deploy_pide_confirmacion(
    git_repo: Path, fake: FakeMoodleProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(git_repo)

    result = runner.invoke(
        app, ["deploy", "--course", COURSE, "--book", BOOK, "--version", "1.0.0"], input="y\n"
    )

    assert result.exit_code == EXIT_OK, result.output
    assert "Continue?" in result.output
    assert fake.get_deploy(int(COURSE), "dwes", "ut03-mvc") is not None


def test_deploy_cancelado_no_despliega(
    git_repo: Path, fake: FakeMoodleProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(git_repo)

    result = runner.invoke(
        app, ["deploy", "--course", COURSE, "--book", BOOK, "--version", "1.0.0"], input="n\n"
    )

    assert result.exit_code == EXIT_OK
    assert "cancelado" in result.output
    assert fake.get_deploy(int(COURSE), "dwes", "ut03-mvc") is None


def test_deploy_rollback_sin_version_ni_ref_usa_latest(
    git_repo: Path, fake: FakeMoodleProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(git_repo)

    result = runner.invoke(app, ["deploy", "--course", COURSE, "--book", BOOK, "--yes"])

    assert result.exit_code == EXIT_OK, result.output
    record = fake.get_deploy(int(COURSE), "dwes", "ut03-mvc")
    assert record is not None
    assert record.content_version == "1.2.0"  # última tag del fixture


def test_deploy_eliminaciones_piden_confirmacion_aparte(
    git_repo: Path, fake: FakeMoodleProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(git_repo)
    runner.invoke(app, ["deploy", "--course", COURSE, "--book", BOOK, "--yes"])
    record = fake.get_deploy(int(COURSE), "dwes", "ut03-mvc")
    assert record is not None
    assert "Observer" in fake.chapter_titles_in_order(record.bookid)

    # Rollback a v1.0.0: primero confirma las eliminaciones, luego el plan.
    result = runner.invoke(
        app,
        ["deploy", "--course", COURSE, "--book", BOOK, "--version", "1.0.0"],
        input="y\ny\n",
    )

    assert result.exit_code == EXIT_OK, result.output
    assert "eliminará 1 capítulo" in result.output
    assert "Observer" not in fake.chapter_titles_in_order(record.bookid)


def test_deploy_book_invalido_exit_2(git_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(git_repo)
    result = runner.invoke(app, ["deploy", "--course", COURSE, "--book", "dwes/ut99", "--yes"])
    assert result.exit_code == EXIT_USAGE


def test_deploy_sin_moodle_env_exit_2(git_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.undo()  # deshace el fake del fixture autouse: _moodle_from_env real
    monkeypatch.delenv("MOODLE_URL", raising=False)
    monkeypatch.delenv("MOODLE_TOKEN", raising=False)
    monkeypatch.chdir(git_repo)
    result = runner.invoke(app, ["deploy", "--course", COURSE, "--book", BOOK, "--yes"])
    assert result.exit_code == EXIT_USAGE
    assert "MOODLE_URL" in result.output


def test_status_tabla_por_book(
    git_repo: Path, fake: FakeMoodleProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(git_repo)
    runner.invoke(
        app, ["deploy", "--course", COURSE, "--book", BOOK, "--version", "1.0.0", "--yes"]
    )

    result = runner.invoke(app, ["status", "--course", COURSE])

    assert result.exit_code == EXIT_OK, result.output
    assert "Book" in result.output and "State" in result.output
    assert "@dwes/ut03-mvc" in result.output
    assert "1.0.0" in result.output
    assert "UPDATE_AVAILABLE" in result.output  # latest taggeada: 1.2.0


def test_status_sin_despliegos(
    git_repo: Path, fake: FakeMoodleProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(git_repo)
    result = runner.invoke(app, ["status", "--course", COURSE])
    assert result.exit_code == EXIT_OK
    assert "no tiene despliegues" in result.output


def test_status_sin_course_exit_2(git_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(git_repo)
    result = runner.invoke(app, ["status"])
    assert result.exit_code == EXIT_USAGE
    assert "--course" in result.output
