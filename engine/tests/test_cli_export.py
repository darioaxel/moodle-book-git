"""Tests del comando ``courseascode export`` (ENG-100, §9).

El cliente Moodle se inyecta mockeando ``_moodle_from_env`` (mismo patrón que
``test_cli_deploy.py``): ningún test toca la red.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from courseascode.cli.main import app
from courseascode.deployment import export_course
from courseascode.moodle import FakeMoodleProvider

runner = CliRunner()

COURSE = "2026"
BOOK = "@dwes/ut03-mvc"
EXIT_OK = 0
EXIT_USAGE = 2


@pytest.fixture()
def fake() -> FakeMoodleProvider:
    fake = FakeMoodleProvider(course_ids=(int(COURSE),))
    fake.add_course(int(COURSE), "DWES 2026-2027", "dwes-2027")
    return fake


@pytest.fixture(autouse=True)
def _moodle_falso(monkeypatch: pytest.MonkeyPatch, fake: FakeMoodleProvider) -> None:
    monkeypatch.setattr("courseascode.cli.main._moodle_from_env", lambda: fake)


def _deploy(git_repo: Path) -> None:
    result = runner.invoke(
        app, ["deploy", "--course", COURSE, "--book", BOOK, "--version", "1.0.0", "--yes"]
    )
    assert result.exit_code == EXIT_OK, result.output


def test_export_genera_yaml_con_el_estado_desplegado(
    git_repo: Path, fake: FakeMoodleProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(git_repo)
    _deploy(git_repo)

    result = runner.invoke(app, ["export", "--course", COURSE])

    assert result.exit_code == EXIT_OK, result.output
    expected = git_repo / "deployments" / f"{COURSE}.yml"
    assert expected.is_file()
    assert str(expected) in result.output

    document = yaml.safe_load(expected.read_text(encoding="utf-8"))
    assert document["format"] == "courseascode-deployments/v1"
    assert document["course"] == {
        "courseid": int(COURSE),
        "shortname": "dwes-2027",
        "fullname": "DWES 2026-2027",
    }
    (entry,) = document["books"]
    record = fake.get_deploy(int(COURSE), "dwes", "ut03-mvc")
    assert record is not None
    assert entry == {
        "source": "dwes",
        "content_id": "ut03-mvc",
        "content_version": "1.0.0",
        "git_ref": "book/ut03-mvc/v1.0.0",
        "git_commit": record.git_commit,
        "deployed_at": record.deployed_at.isoformat(),
        "deployed_by": "cli",
        "status": "success",
    }


def test_export_reexport_es_byte_exacto(
    git_repo: Path, fake: FakeMoodleProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(git_repo)
    _deploy(git_repo)
    first = export_course(fake, int(COURSE), Path("deployments")).read_bytes()
    second = export_course(fake, int(COURSE), Path("deployments")).read_bytes()
    assert first == second


def test_export_multiples_books_orden_estable(
    git_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(git_repo)
    _deploy(git_repo)
    result = runner.invoke(app, ["deploy", "--course", COURSE, "--book", "@dwes/ut04-dao", "--yes"])
    assert result.exit_code == EXIT_OK, result.output

    result = runner.invoke(app, ["export", "--course", COURSE])
    assert result.exit_code == EXIT_OK, result.output
    first = (git_repo / "deployments" / f"{COURSE}.yml").read_bytes()
    runner.invoke(app, ["export", "--course", COURSE])
    second = (git_repo / "deployments" / f"{COURSE}.yml").read_bytes()
    assert first == second
    document = yaml.safe_load(first.decode("utf-8"))
    assert [b["content_id"] for b in document["books"]] == ["ut03-mvc", "ut04-dao"]


def test_export_curso_inexistente_exit_2(monkeypatch: pytest.MonkeyPatch) -> None:
    result = runner.invoke(app, ["export", "--course", "999"])
    assert result.exit_code == EXIT_USAGE
    assert "no existe el curso 999" in result.output


def test_export_curso_no_numerico_exit_2() -> None:
    result = runner.invoke(app, ["export", "--course", "dwes"])
    assert result.exit_code == EXIT_USAGE
