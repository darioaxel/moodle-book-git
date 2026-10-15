"""Tests unitarios del ``Executor`` (ENG-073, ENG-077)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from courseascode.deployment import Executor, Planner, deserialize_hashes, hash_html
from courseascode.deployment.hashes import hash_bytes, serialize_hashes
from courseascode.domain.content import Numbering
from courseascode.domain.deployment import (
    ActionKind,
    DeploymentAction,
    DeploymentPlan,
)
from courseascode.domain.identity import ContentId
from courseascode.domain.semver import SemVer
from courseascode.moodle import DeployRecord, FakeMoodleProvider
from tests.deployment_factory import build_book

COURSE = 101
SOURCE = "dwes"
BOOK = "ut03-mvc"
SHA_LENGTH = 40


def _plan(actions: tuple[DeploymentAction, ...], version: str = "1.0.0") -> DeploymentPlan:
    return DeploymentPlan(
        course_id=COURSE,
        content=ContentId(SOURCE, BOOK),
        current_version=None,
        target_version=SemVer.parse(version),
        actions=actions,
        git_ref=f"book/{BOOK}/v{version}",
        git_commit="a" * 40,
    )


def _chapter(
    kind: ActionKind, stable_id: str, title: str, html: str, position: int
) -> DeploymentAction:
    return DeploymentAction(
        kind=kind, target="chapter", stable_id=stable_id, title=title, html=html, position=position
    )


def _base_plan(html_by_id: dict[str, str] | None = None) -> DeploymentPlan:
    html_by_id = html_by_id or {
        "introduccion": "<h1>Intro</h1>",
        "mvc": '<h1>MVC</h1><a href="#chapter-model">Model</a>',
        "model": "<h1>Model</h1>",
    }
    titles = {"introduccion": "Introducción", "mvc": "MVC", "model": "Model"}
    actions = [
        DeploymentAction(
            kind=ActionKind.CREATE,
            target="book",
            title="MVC y patrones de diseño",
            html="<p>Intro</p>",
            numbering="numbers",
        )
    ]
    actions += [
        _chapter(ActionKind.CREATE, sid, titles[sid], html_by_id[sid], pos)
        for pos, sid in enumerate(html_by_id, start=1)
    ]
    return _plan(tuple(actions))


def test_ejecuta_crea_book_capitulos_en_orden_y_registra(tmp_path: Path) -> None:
    fake = FakeMoodleProvider(course_ids=(COURSE,))
    plan = _base_plan()

    result = Executor(fake).execute(plan, deployed_by="tester")

    assert result.success
    assert result.version == "1.0.0"
    assert result.commit == "a" * SHA_LENGTH
    record = fake.get_deploy(COURSE, SOURCE, BOOK)
    assert record is not None
    assert record.deployed_by == "tester"
    assert record.content_version == "1.0.0"
    assert record.bookid >= 1
    assert fake.chapter_titles_in_order(record.bookid) == ["Introducción", "MVC", "Model"]
    # content_hash = estado final desplegado, por capítulo (ENG-073). El HTML
    # del que se hashea es el final: placeholders de enlaces ya resueltos.
    stored = deserialize_hashes(record.content_hash)
    assert stored == {
        sid: hash_html(fake.chapter_html(record.bookid, sid))
        for sid in ("introduccion", "mvc", "model")
    }


def test_reejecutar_el_mismo_plan_no_duplica() -> None:
    fake = FakeMoodleProvider(course_ids=(COURSE,))
    plan = _base_plan()
    first = Executor(fake).execute(plan)
    record = fake.get_deploy(COURSE, SOURCE, BOOK)
    assert record is not None

    second = Executor(fake).execute(plan)

    assert second.success
    assert fake.chapter_titles_in_order(record.bookid) == ["Introducción", "MVC", "Model"]
    TWO_DEPLOYS = 2
    assert len(fake.list_deploys(COURSE)) == TWO_DEPLOYS  # historial, no duplicados
    assert first.actions_applied == second.actions_applied


def test_resuelve_placeholders_de_enlaces_en_el_mismo_deploy() -> None:
    """Los ``#chapter-<id>`` quedan con URL real tras el deploy (§16, ENG-077)."""
    fake = FakeMoodleProvider(course_ids=(COURSE,))
    plan = _base_plan()
    Executor(fake).execute(plan)
    record = fake.get_deploy(COURSE, SOURCE, BOOK)
    assert record is not None

    mvc_html = fake.chapter_html(record.bookid, "mvc")

    assert "#chapter-model" not in mvc_html
    assert "mod/book/view.php" in mvc_html
    # El hash registrado es sobre el HTML final (ya resuelto).
    assert json.loads(record.content_hash)["mvc"] == hash_html(mvc_html)


def test_eliminaciones_sin_confirmacion_se_omiten_con_aviso() -> None:
    fake = FakeMoodleProvider(course_ids=(COURSE,))
    Executor(fake).execute(_base_plan())

    plan_v2 = _plan(
        (
            DeploymentAction(
                kind=ActionKind.DELETE,
                target="chapter",
                stable_id="model",
                title="Model",
                requires_confirmation=True,
            ),
        ),
        version="1.1.0",
    )
    result = Executor(fake).execute(plan_v2)  # sin confirmed_deletions

    assert result.success
    record = fake.get_deploy(COURSE, SOURCE, BOOK)
    assert record is not None
    remote = fake.get_book(record.bookid)
    assert remote is not None
    assert "model" in remote.chapters  # no se borró
    assert any("sin confirmación" in warning for warning in result.warnings)
    assert not any(action.kind is ActionKind.DELETE for action in result.actions_applied)


def test_eliminaciones_con_confirmacion_borran() -> None:
    fake = FakeMoodleProvider(course_ids=(COURSE,))
    Executor(fake).execute(_base_plan())

    plan_v2 = _plan(
        (
            DeploymentAction(
                kind=ActionKind.DELETE,
                target="chapter",
                stable_id="model",
                title="Model",
                requires_confirmation=True,
            ),
        ),
        version="1.1.0",
    )
    Executor(fake).execute(plan_v2, confirmed_deletions=True)

    record = fake.get_deploy(COURSE, SOURCE, BOOK)
    assert record is not None
    remote = fake.get_book(record.bookid)
    assert remote is not None
    assert "model" not in remote.chapters
    # El hash registrado ya no incluye el capítulo eliminado.
    assert set(deserialize_hashes(record.content_hash)) == {"introduccion", "mvc"}


def test_upload_con_datos_sube_el_asset() -> None:
    fake = FakeMoodleProvider(course_ids=(COURSE,))
    plan = _base_plan()
    plan = plan.model_copy(
        update={
            "actions": [
                *plan.actions,
                DeploymentAction(
                    kind=ActionKind.UPLOAD,
                    target="asset",
                    asset_path="assets/mvc.svg",
                    asset_data=b"<svg/>",
                ),
            ]
        }
    )

    result = Executor(fake).execute(plan)

    record = fake.get_deploy(COURSE, SOURCE, BOOK)
    assert record is not None
    remote = fake.get_book(record.bookid)
    assert remote is not None
    assert remote.assets["mvc.svg"] == hash_bytes(b"<svg/>")
    assert any(action.kind is ActionKind.UPLOAD for action in result.actions_applied)


def test_hash_mal_formado_no_rompe_el_estado() -> None:
    """Un content_hash corrupto del registro previo no rompe la reejecución."""
    fake = FakeMoodleProvider(course_ids=(COURSE,))
    bookid = fake.upsert_book(COURSE, "MVC y patrones de diseño", "<p>Intro</p>", Numbering.NUMBERS)
    fake.upsert_chapter(bookid, "introduccion", "Introducción", "<h1>Intro</h1>", 1)
    fake.register_deploy(
        DeployRecord(
            courseid=COURSE,
            bookid=bookid,
            source=SOURCE,
            content_id=BOOK,
            content_version="1.0.0",
            git_ref=f"book/{BOOK}/v1.0.0",
            git_commit="b" * 40,
            content_hash="no-es-json",
            deployed_at=datetime(2026, 1, 1, tzinfo=UTC),
            deployed_by="tester",
        )
    )

    plan = _base_plan()
    result = Executor(fake).execute(plan)

    assert result.success
    record = fake.get_deploy(COURSE, SOURCE, BOOK)
    assert record is not None
    stored = deserialize_hashes(record.content_hash)
    assert set(stored) == {"introduccion", "mvc", "model"}


def test_plan_con_target_renderizado_e2e_minimo(tmp_path: Path) -> None:
    """Planner + executor sobre un RenderedBook real: el estado quede exacto."""
    fake = FakeMoodleProvider(course_ids=(COURSE,))
    target = build_book(
        tmp_path,
        {
            "01-intro.md": "# Intro\n",
            "02-mvc.md": "# MVC\n",
            "03-model.md": "# Model\n",
        },
    )
    plan = Planner(fake).plan(COURSE, SOURCE, BOOK, target, SemVer.parse("1.0.0"))

    result = Executor(fake).execute(plan)

    assert result.success
    record = fake.get_deploy(COURSE, SOURCE, BOOK)
    assert record is not None
    assert record.content_hash == serialize_hashes(
        {c.stable_id: hash_html(c.html) for c in target.chapters}
    )
