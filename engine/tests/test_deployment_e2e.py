"""E2E del ciclo deploy → update → rollback → drift → eliminación (ENG-080, §32).

Todo el ciclo corre contra ``FakeMoodleProvider`` y el fixture ``git_repo``
(tags ``book/ut03-mvc/v1.0.0`` → v1.1.0 → v1.2.0). Los criterios de §32 que
requieren moodle-docker 🔌 (ciclo de importación con plugin real) quedan para
la suite ``integration`` de la Fase 9 (ENG-104).

Cobertura contra el fake:

- Ciclo básico (§32 pasos 5-6): deploy v1.0.0 con imágenes y enlaces internos.
- Ciclo de actualización (§32 pasos 7-10): UPDATE sin duplicados.
- Ciclo de rollback (§32 paso 11): el estado queda *exactamente* igual que un
  deploy limpio de esa versión.
- Drift (§19.1), eliminación con confirmación (§17.2), idempotencia (§17.3).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from courseascode.deployment import (
    DeploymentService,
    RecalledVersionError,
    deserialize_hashes,
)
from courseascode.domain.deployment import ActionKind, DeploymentState, Severity
from courseascode.domain.semver import SemVer
from courseascode.git import LocalGitProvider
from courseascode.moodle import DeployRecord, FakeMoodleProvider
from tests.deployment_factory import MemoryReleasePort

COURSE = 2026
OTHER_COURSE = 2027
SOURCE = "dwes"
BOOK = "ut03-mvc"
SHA_LENGTH = 40

V1_TITLES = ["Introducción", "MVC", "Model", "View", "Controller"]
V1_CHAPTER_IDS = ["introduccion", "mvc", "model", "view", "controller"]
# Orden del manifest en v1.1.0: observer se añade al final (06-observer.md).
V2_TITLES = [*V1_TITLES, "Observer"]


@pytest.fixture()
def service(git_repo: Path) -> tuple[DeploymentService, FakeMoodleProvider]:
    fake = FakeMoodleProvider(course_ids=(COURSE, OTHER_COURSE))
    deployment = DeploymentService(LocalGitProvider(git_repo), fake, source=SOURCE)
    return deployment, fake


def _record(fake: FakeMoodleProvider, courseid: int = COURSE) -> DeployRecord:
    record = fake.get_deploy(courseid, SOURCE, BOOK)
    assert record is not None
    return record


def _chapter_map(fake: FakeMoodleProvider, bookid: int) -> dict[str, str]:
    """HTML por stable id tal como está en Moodle."""
    remote = fake.get_book(bookid)
    assert remote is not None
    return {sid: chapter.html for sid, chapter in remote.chapters.items()}


def test_ciclo_basico_despliegue_v1(service: tuple[DeploymentService, FakeMoodleProvider]) -> None:
    deployment, fake = service

    result = deployment.deploy(COURSE, BOOK, version="1.0.0", assume_yes=True, deployed_by="test")

    assert result.success
    assert result.version == "1.0.0"
    record = _record(fake)
    # §32 paso 6: la tabla registra source, content_id, versión y commit.
    assert record.source == SOURCE
    assert record.content_id == BOOK
    assert record.content_version == "1.0.0"
    assert len(record.git_commit) == SHA_LENGTH
    assert record.git_ref == f"book/{BOOK}/v1.0.0"

    # El Book Moodle tiene los capítulos en el orden del manifest.
    assert fake.chapter_titles_in_order(record.bookid) == V1_TITLES

    # Imágenes con URL pluginfile real (dos pasadas, ENG-072)…
    mvc_html = fake.chapter_html(record.bookid, "mvc")
    assert f"/pluginfile.php/{record.bookid}/" in mvc_html and "mvc.svg" in mvc_html
    view_html = fake.chapter_html(record.bookid, "view")
    assert "ejemplo.png" in view_html
    # …y assets subidos con su contenido.
    book = fake.get_book(record.bookid)
    assert book is not None
    assert set(book.assets) == {"mvc.svg", "ejemplo.png"}

    # Enlaces internos resueltos a URL de capítulo, sin placeholders (§16).
    assert "#chapter-" not in mvc_html
    assert "mod/book/view.php" in mvc_html

    # content_hash registrado = estado final por capítulo.
    stored = deserialize_hashes(record.content_hash)
    assert set(stored) == set(V1_CHAPTER_IDS)


def test_actualizacion_sin_duplicados(
    service: tuple[DeploymentService, FakeMoodleProvider],
) -> None:
    deployment, fake = service
    deployment.deploy(COURSE, BOOK, version="1.0.0", assume_yes=True)

    # Sin --version: última versión disponible (§17 paso 1).
    result = deployment.deploy(COURSE, BOOK, assume_yes=True)

    assert result.version == "1.2.0"
    record = _record(fake)
    # §32 paso 10: el MISMO Book se actualiza (mismo bookid, sin duplicados).
    assert record.content_version == "1.2.0"
    assert fake.chapter_titles_in_order(record.bookid) == V2_TITLES  # v1.2.0 incluye observer
    TWO_DEPLOYS = 2
    assert len(fake.list_deploys(COURSE)) == TWO_DEPLOYS  # historial: un registro por deploy


def test_update_dispara_create_y_update(
    service: tuple[DeploymentService, FakeMoodleProvider],
) -> None:
    deployment, fake = service
    deployment.deploy(COURSE, BOOK, version="1.0.0", assume_yes=True)

    plan = deployment.plan(COURSE, BOOK, version="1.1.0")

    # §17.1: el plan refleja el diff (observer es nuevo, mvc cambió).
    by_id = {a.stable_id: a.kind for a in plan.actions if a.target == "chapter"}
    assert by_id["observer"] is ActionKind.CREATE
    assert by_id["mvc"] is ActionKind.UPDATE
    assert "model" not in by_id and "introduccion" not in by_id
    assert any("+ 06-observer.md" in change for change in plan.changes)
    assert any(change.startswith("~ 02-mvc.md") for change in plan.changes)
    assert not plan.has_deletions

    deployment.deploy(COURSE, BOOK, version="1.1.0", assume_yes=True)
    record = _record(fake)
    assert fake.chapter_titles_in_order(record.bookid) == V2_TITLES


def test_rollback_restaura_el_estado_exacto(
    service: tuple[DeploymentService, FakeMoodleProvider],
) -> None:
    """§32 paso 11 / ENG-077: v1.2.0 → v1.1.0 deja el Book *exactamente* como
    estaba tras el deploy de v1.1.0 (mismos capítulos, mismo HTML, mismos
    assets, mismo content_hash)."""
    deployment, fake = service
    deployment.deploy(COURSE, BOOK, version="1.0.0", assume_yes=True)
    deployment.deploy(COURSE, BOOK, version="1.1.0", assume_yes=True)
    bookid = _record(fake).bookid
    snapshot = _chapter_map(fake, bookid)
    snapshot_assets = fake.get_book(bookid).assets  # type: ignore[union-attr]
    snapshot_hash = _record(fake).content_hash

    deployment.deploy(COURSE, BOOK, version="1.2.0", assume_yes=True)

    # Rollback: mismo pipeline, sin código especial (§18).
    result = deployment.deploy(COURSE, BOOK, version="1.1.0", assume_yes=True)

    assert result.version == "1.1.0"
    record = _record(fake)
    assert record.bookid == bookid  # el MISMO Book Moodle (§32 paso 10)
    assert record.content_version == "1.1.0"
    assert fake.chapter_titles_in_order(record.bookid) == V2_TITLES
    assert _chapter_map(fake, record.bookid) == snapshot
    assert fake.get_book(record.bookid).assets == snapshot_assets  # type: ignore[union-attr]
    assert record.content_hash == snapshot_hash


def test_drift_por_edicion_manual_y_sobrescritura(
    service: tuple[DeploymentService, FakeMoodleProvider],
) -> None:
    deployment, fake = service
    deployment.deploy(COURSE, BOOK, assume_yes=True)
    record = _record(fake)

    fake.mutate_chapter(record.bookid, "model", "<h1>Model EDITADO A MANO</h1>")

    info = deployment.state(COURSE, BOOK)
    assert info.state is DeploymentState.DRIFT_DETECTED
    assert "model" in info.detail

    # Redeploy de la misma versión: el plan incluye el UPDATE que sobrescribe
    # la edición manual (§19.1).
    plan = deployment.plan(COURSE, BOOK)
    by_id = {a.stable_id: a.kind for a in plan.actions if a.target == "chapter"}
    assert by_id.get("model") is ActionKind.UPDATE

    deployment.deploy(COURSE, BOOK, assume_yes=True)
    assert "<h1>Model EDITADO A MANO</h1>" not in fake.chapter_html(record.bookid, "model")
    assert deployment.state(COURSE, BOOK).state is DeploymentState.UP_TO_DATE


def test_eliminaciones_requieren_confirmacion(
    service: tuple[DeploymentService, FakeMoodleProvider],
) -> None:
    deployment, fake = service
    deployment.deploy(COURSE, BOOK, assume_yes=True)  # v1.2.0, con observer
    record = _record(fake)

    # v1.0.0 no tiene observer: el plan lo marca DELETE con confirmación (§17.2).
    plan = deployment.plan(COURSE, BOOK, version="1.0.0")
    deletions = [a for a in plan.actions if a.kind is ActionKind.DELETE]
    assert [a.stable_id for a in deletions] == ["observer"]
    assert all(a.requires_confirmation for a in deletions)

    # Sin confirmación: no se borra y el resultado lo advierte.
    result = deployment.deploy(COURSE, BOOK, version="1.0.0")
    assert result.success
    remote = fake.get_book(record.bookid)
    assert remote is not None
    assert "observer" in remote.chapters  # no se borró
    assert any("sin confirmación" in warning for warning in result.warnings)

    # Con confirmación: se borra y el estado queda exactamente en v1.0.0.
    result = deployment.deploy(COURSE, BOOK, version="1.0.0", assume_yes=True)
    assert result.success
    assert fake.chapter_titles_in_order(record.bookid) == V1_TITLES
    assert set(_chapter_map(fake, record.bookid)) == set(V1_CHAPTER_IDS)


def test_redeploy_idempotente_plan_vacio(
    service: tuple[DeploymentService, FakeMoodleProvider],
) -> None:
    """§17.3: publicar dos veces la misma versión no duplica nada."""
    deployment, fake = service
    deployment.deploy(COURSE, BOOK, version="1.0.0", assume_yes=True)
    record = _record(fake)

    plan = deployment.plan(COURSE, BOOK, version="1.0.0")
    assert plan.actions == ()
    result = deployment.deploy(COURSE, BOOK, version="1.0.0", assume_yes=True)

    assert result.actions_applied == ()
    assert "nada que hacer" in result.message
    assert fake.chapter_titles_in_order(record.bookid) == V1_TITLES
    assert len(fake.list_deploys(COURSE)) == 1  # sin registro extra


def test_version_recallada_bloquea_y_force_despliega(
    git_repo: Path,
) -> None:
    fake = FakeMoodleProvider(course_ids=(COURSE,))
    releases = MemoryReleasePort(
        recalled={(SOURCE, BOOK, "1.0.0")},
        severities={(SOURCE, BOOK, "1.0.0"): Severity.CRITICAL},
    )
    deployment = DeploymentService(LocalGitProvider(git_repo), fake, releases, source=SOURCE)

    with pytest.raises(RecalledVersionError, match="RECALLED"):
        deployment.deploy(COURSE, BOOK, version="1.0.0", assume_yes=True)

    result = deployment.deploy(COURSE, BOOK, version="1.0.0", assume_yes=True, force=True)
    assert result.success
    assert any("RECALLED" in warning for warning in result.warnings)


def test_status_muestra_update_available_con_severidad(git_repo: Path) -> None:
    fake = FakeMoodleProvider(course_ids=(COURSE,))
    releases = MemoryReleasePort(severities={(SOURCE, BOOK, "1.2.0"): Severity.CRITICAL})
    deployment = DeploymentService(LocalGitProvider(git_repo), fake, releases, source=SOURCE)
    deployment.deploy(COURSE, BOOK, version="1.0.0", assume_yes=True)

    rows = deployment.course_status(COURSE)

    assert len(rows) == 1
    row = rows[0]
    assert str(row.content) == f"@{SOURCE}/{BOOK}"
    assert row.state.state is DeploymentState.UPDATE_AVAILABLE
    assert row.state.severity is Severity.CRITICAL
    assert row.state.version == SemVer.parse("1.0.0")


def test_where_localiza_cursos_con_la_version(
    service: tuple[DeploymentService, FakeMoodleProvider],
) -> None:
    deployment, _fake = service
    deployment.deploy(COURSE, BOOK, version="1.0.0", assume_yes=True)

    assert deployment.where(SOURCE, BOOK, "1.0.0") == [COURSE]
    assert deployment.where(SOURCE, BOOK, "1.1.0") == []
