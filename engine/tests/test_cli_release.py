"""Tests del CLI ``courseascode release mark/list`` (ENG-091).

El store es SQLite sobre ``tmp_path`` vía ``COURSEASCODE_DB`` y el token de
coordinador vía ``COURSEASCODE_ADMIN_TOKEN`` (env del operador, §25). Ningún
test toca Moodle: solo el subcomando ``release``.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from courseascode.cli.main import app
from courseascode.releases import ReleaseStore

runner = CliRunner()

BOOK = "ut03-mvc"
REF = f"book/{BOOK}/v1.3.0"
ADMIN_TOKEN = "token-coordinador-test"
SOURCE = "dwes"

EXIT_OK = 0
EXIT_USAGE = 2
EXIT_AUTH = 3


@pytest.fixture()
def db_url(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    url = f"sqlite:///{tmp_path / 'cli.db'}"
    monkeypatch.setenv("COURSEASCODE_DB", url)
    return url


@pytest.fixture()
def authorized(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COURSEASCODE_ADMIN_TOKEN", ADMIN_TOKEN)


def test_mark_sin_token_configurado_sale_con_error_claro(db_url: str) -> None:
    result = runner.invoke(app, ["release", "mark", REF])

    assert result.exit_code == EXIT_AUTH
    assert "COURSEASCODE_ADMIN_TOKEN" in result.output


def test_mark_con_token_incorrecto_sale_con_error_claro(db_url: str, authorized: None) -> None:
    result = runner.invoke(app, ["release", "mark", REF, "--token", "otro-token"])

    assert result.exit_code == EXIT_AUTH
    assert "incorrecto" in result.output


def test_mark_critical_exige_reason(db_url: str, authorized: None) -> None:
    result = runner.invoke(app, ["release", "mark", REF, "--severity", "critical"])

    assert result.exit_code == EXIT_USAGE
    assert "--reason" in result.output


def test_mark_recall_exige_reason(db_url: str, authorized: None) -> None:
    result = runner.invoke(app, ["release", "mark", REF, "--recall"])

    assert result.exit_code == EXIT_USAGE
    assert "--reason" in result.output


def test_mark_con_severidad_invalida_sale_con_error_claro(db_url: str, authorized: None) -> None:
    result = runner.invoke(app, ["release", "mark", REF, "--severity", "grave", "--reason", "x"])

    assert result.exit_code == EXIT_USAGE
    assert "normal o critical" in result.output


def test_mark_con_ref_invalido_sale_con_error_claro(db_url: str, authorized: None) -> None:
    result = runner.invoke(app, ["release", "mark", "v1.3.0"])

    assert result.exit_code == EXIT_USAGE
    assert "book/<id>/vX.Y.Z" in result.output


def test_mark_escribe_en_sqlite_y_audita(db_url: str, authorized: None) -> None:
    reason = "El ejemplo del patrón Active Record contenía SQL inseguro"
    result = runner.invoke(
        app,
        [
            "release",
            "mark",
            REF,
            "--severity",
            "critical",
            "--fixed-in",
            "1.3.1",
            "--reason",
            reason,
        ],
    )

    assert result.exit_code == EXIT_OK, result.output
    assert "RECALLED" not in result.output  # sin --recall: solo severidad crítica
    store = ReleaseStore(db_url)
    info = store.get(REF, source=SOURCE)
    assert info is not None
    assert info.severity == "critical"
    assert info.recalled is False
    assert info.fixed_in == "1.3.1"
    assert info.reason == reason
    assert info.marked_by == "coordinator"
    events = store.audit(book_id=BOOK)
    assert len(events) == 1
    assert events[0].event_type == "release.mark"
    assert events[0].detail["reason"] == reason


def test_mark_recall_retira_la_version(db_url: str, authorized: None) -> None:
    result = runner.invoke(app, ["release", "mark", REF, "--recall", "--reason", "error grave"])

    assert result.exit_code == EXIT_OK, result.output
    assert "RECALLED" in result.output
    info = ReleaseStore(db_url).get(REF, source=SOURCE)
    assert info is not None
    assert info.recalled is True


def test_mark_normal_no_exige_reason(db_url: str, authorized: None) -> None:
    result = runner.invoke(app, ["release", "mark", REF])

    assert result.exit_code == EXIT_OK, result.output
    info = ReleaseStore(db_url).get(REF, source=SOURCE)
    assert info is not None
    assert info.severity == "normal"


def test_list_vacio_avisa(db_url: str, authorized: None) -> None:
    result = runner.invoke(app, ["release", "list", BOOK])

    assert result.exit_code == EXIT_OK
    assert "Sin releases marcadas" in result.output


def test_list_muestra_tabla_de_releases(db_url: str, authorized: None) -> None:
    runner.invoke(
        app,
        [
            "release",
            "mark",
            REF,
            "--severity",
            "critical",
            "--fixed-in",
            "1.3.1",
            "--reason",
            "SQL inseguro",
        ],
    )
    runner.invoke(
        app,
        ["release", "mark", f"book/{BOOK}/v1.3.1", "--reason", "hotfix publicado"],
    )

    result = runner.invoke(app, ["release", "list", BOOK])

    assert result.exit_code == EXIT_OK, result.output
    assert REF in result.output
    assert "CRITICAL" in result.output
    assert "1.3.1" in result.output
    assert "coordinator" in result.output


def test_list_filtra_por_fuente_con_contentid(db_url: str, authorized: None) -> None:
    runner.invoke(app, ["release", "mark", REF, "--reason", "marca en la oficial"])

    oficiales = runner.invoke(app, ["release", "list", "@dwes/ut03-mvc"])
    vacio = runner.invoke(app, ["release", "list", "@fork-juan/ut03-mvc"])

    assert REF in oficiales.output
    assert "Sin releases marcadas" in vacio.output
