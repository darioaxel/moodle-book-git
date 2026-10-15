"""Tests unitarios del ``Planner`` (ENG-070, ENG-071, ENG-075)."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from courseascode.deployment import Planner, RecalledVersionError
from courseascode.deployment.executor import Executor
from courseascode.domain.deployment import ActionKind
from courseascode.domain.semver import SemVer
from courseascode.moodle import FakeMoodleProvider
from tests.deployment_factory import BOOK_YML, MemoryReleasePort, build_book

COURSE = 101
SOURCE = "dwes"
BOOK = "ut03-mvc"

V1_FILES = {
    "01-intro.md": "# Intro\n",
    "02-mvc.md": "# MVC\n",
    "03-model.md": "# Model\n",
}
V2_FILES = {
    **V1_FILES,
    "02-mvc.md": "# MVC\n\nMás detalle.\n",  # modificado
    "04-view.md": "# View\n",  # nuevo
}
BOOK_YML_V2 = BOOK_YML + "  - id: view\n    title: View\n    file: 04-view.md\n"


def _service() -> tuple[FakeMoodleProvider, Planner]:
    fake = FakeMoodleProvider(course_ids=(COURSE,))
    return fake, Planner(fake)


def _deployed(
    fake: FakeMoodleProvider, tmp_path: Path, files: dict[str, str], book_yml: str | None = None
) -> None:
    """Deja el fake en el estado de un deploy ya hecho de ``files`` (v1.0.0)."""
    target = build_book(tmp_path, files, book_yml=book_yml)
    plan = Planner(fake).plan(COURSE, SOURCE, BOOK, target, SemVer.parse("1.0.0"))
    Executor(fake).execute(plan, confirmed_deletions=True)


def test_primer_deploy_todo_create(tmp_path: Path) -> None:
    _fake, planner = _service()
    target = build_book(tmp_path / "book", V1_FILES)

    plan = planner.plan(COURSE, SOURCE, BOOK, target, SemVer.parse("1.0.0"))

    assert plan.current_version is None
    kinds = [action.kind for action in plan.actions]
    FIRST_DEPLOY_CREATES = 4  # book + 3 capítulos
    assert kinds.count(ActionKind.CREATE) == FIRST_DEPLOY_CREATES
    positions = {
        action.stable_id: action.position for action in plan.actions if action.target == "chapter"
    }
    assert positions == {"introduccion": 1, "mvc": 2, "model": 3}
    book = next(action for action in plan.actions if action.target == "book")
    assert book.kind is ActionKind.CREATE
    assert book.html  # la intro llega renderizada


def test_plan_vacio_cuando_todo_coincide(tmp_path: Path) -> None:
    _fake, planner = _service()
    _deployed(_fake, tmp_path / "v1", V1_FILES)
    target = build_book(tmp_path / "v1bis", V1_FILES)

    plan = planner.plan(COURSE, SOURCE, BOOK, target, SemVer.parse("1.0.0"))

    assert plan.actions == ()
    assert not plan.requires_confirmation
    assert plan.current_version == SemVer.parse("1.0.0")


def test_update_y_create_solo_donde_cambia(tmp_path: Path) -> None:
    fake, planner = _service()
    _deployed(fake, tmp_path / "v1", V1_FILES)
    target = build_book(tmp_path / "v2", V2_FILES, book_yml=BOOK_YML_V2)

    plan = planner.plan(COURSE, SOURCE, BOOK, target, SemVer.parse("1.1.0"))

    by_id = {action.stable_id: action for action in plan.actions if action.target == "chapter"}
    assert set(by_id) == {"mvc", "view"}
    assert by_id["mvc"].kind is ActionKind.UPDATE
    assert by_id["view"].kind is ActionKind.CREATE
    VIEW_POSITION = 4
    assert by_id["view"].position == VIEW_POSITION
    # introduccion y model no cambian: sin acción.
    assert "introduccion" not in by_id and "model" not in by_id


def test_eliminacion_requiere_confirmacion(tmp_path: Path) -> None:
    fake, planner = _service()
    _deployed(fake, tmp_path / "v2", V2_FILES, book_yml=BOOK_YML_V2)
    target = build_book(tmp_path / "v1", V1_FILES)  # vuelve a v1: falta "view"

    plan = planner.plan(COURSE, SOURCE, BOOK, target, SemVer.parse("1.0.0"))

    assert plan.has_deletions
    deletions = [action for action in plan.actions if action.kind is ActionKind.DELETE]
    assert len(deletions) == 1
    assert deletions[0].stable_id == "view"
    assert all(action.requires_confirmation for action in deletions)


def test_update_del_book_si_cambia_el_titulo(tmp_path: Path) -> None:
    fake, planner = _service()
    _deployed(fake, tmp_path / "v1", V1_FILES)
    target = build_book(tmp_path / "v2", V1_FILES)
    renamed = target.book.model_copy(update={"title": "MVC (2ª edición)"})
    target = replace(target, book=renamed)

    plan = planner.plan(COURSE, SOURCE, BOOK, target, SemVer.parse("1.0.1"))

    book_actions = [action for action in plan.actions if action.target == "book"]
    assert len(book_actions) == 1
    assert book_actions[0].kind is ActionKind.UPDATE


def test_uploads_documentados_en_el_plan(tmp_path: Path) -> None:
    fake, planner = _service()
    _deployed(fake, tmp_path / "v1", V1_FILES)
    target = build_book(tmp_path / "v2", V2_FILES, book_yml=BOOK_YML_V2)

    plan = planner.plan(
        COURSE,
        SOURCE,
        BOOK,
        target,
        SemVer.parse("1.1.0"),
        uploaded_assets=["assets/mvc.svg"],
    )

    uploads = [action for action in plan.actions if action.kind is ActionKind.UPLOAD]
    assert [action.asset_path for action in uploads] == ["assets/mvc.svg"]


def test_version_recallada_bloquea_y_force_avisa(tmp_path: Path) -> None:
    fake = FakeMoodleProvider(course_ids=(COURSE,))
    releases = MemoryReleasePort(recalled={(SOURCE, BOOK, "1.1.0")})
    planner = Planner(fake, releases)
    target = build_book(tmp_path / "v2", V2_FILES, book_yml=BOOK_YML_V2)

    with pytest.raises(RecalledVersionError, match="RECALLED"):
        planner.plan(COURSE, SOURCE, BOOK, target, SemVer.parse("1.1.0"))

    plan = planner.plan(COURSE, SOURCE, BOOK, target, SemVer.parse("1.1.0"), force=True)
    assert plan.actions  # ejecutable con force…
    assert any("RECALLED" in warning for warning in plan.warnings)  # …con aviso


def test_summary_incluye_changes_y_advertencia_de_eliminaciones(tmp_path: Path) -> None:
    fake, planner = _service()
    _deployed(fake, tmp_path / "v2", V2_FILES, book_yml=BOOK_YML_V2)
    target = build_book(tmp_path / "v1", V1_FILES)

    plan = planner.plan(COURSE, SOURCE, BOOK, target, SemVer.parse("1.0.0"))
    plan = plan.model_copy(update={"changes": ("+ 04-view.md",)})

    summary = plan.summary()
    assert "Changes:" in summary
    assert "+ 04-view.md" in summary
    assert "eliminará 1 capítulo" in summary
