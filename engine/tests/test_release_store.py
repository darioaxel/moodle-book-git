"""Tests de ``ReleaseStore`` (SQLite) y ``SqlReleasePort`` (ENG-090/092/095).

SQLite sobre ``tmp_path``: sin servicios externos. El port SQL se inyecta en
un ``DeploymentService`` real (Git fixture + ``FakeMoodleProvider``) para
verificar el circuito completo: severidad → badge de estado, recall → bloqueo
del planner (ENG-075) y auditoría de deploys.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from courseascode.deployment import DeploymentService, RecalledVersionError
from courseascode.domain.deployment import DeploymentState, Severity
from courseascode.domain.semver import SemVer
from courseascode.git import LocalGitProvider
from courseascode.moodle import FakeMoodleProvider
from courseascode.releases import ReleaseStore, ReleaseStoreError, SqlReleasePort

COURSE = 2026
SOURCE = "dwes"
BOOK = "ut03-mvc"
REF = f"book/{BOOK}/v1.3.0"


@pytest.fixture()
def store(tmp_path: Path) -> ReleaseStore:
    return ReleaseStore(f"sqlite:///{tmp_path / 'releases.db'}")


def _mark(store: ReleaseStore, ref: str = REF, **overrides: object) -> None:
    values: dict[str, object] = {
        "source": SOURCE,
        "severity": Severity.NORMAL,
        "recalled": False,
        "fixed_in": None,
        "reason": None,
        "marked_by": "coordinator",
    }
    values.update(overrides)
    store.mark(ref, **values)  # type: ignore[arg-type]


def test_mark_crea_la_release_y_get_la_devuelve(store: ReleaseStore) -> None:
    info = store.mark(
        REF,
        source=SOURCE,
        severity=Severity.CRITICAL,
        recalled=True,
        fixed_in="1.3.1",
        reason="SQL inseguro en el ejemplo",
        marked_by="coordinator",
    )

    assert info.ref == REF
    assert info.book_id == BOOK
    assert info.version == "1.3.0"
    assert info.severity == "critical"
    assert info.recalled is True
    assert info.fixed_in == "1.3.1"
    assert info.reason == "SQL inseguro en el ejemplo"
    assert info.marked_by == "coordinator"
    fetched = store.get(REF, source=SOURCE)
    assert fetched == info


def test_mark_es_upsert_por_ref(store: ReleaseStore) -> None:
    _mark(store, reason="primera marca")
    again = store.mark(
        REF,
        source=SOURCE,
        severity=Severity.CRITICAL,
        recalled=True,
        fixed_in="1.3.1",
        reason="segunda marca",
        marked_by="coordinator",
    )

    releases = store.list_for(BOOK)
    assert len(releases) == 1  # no duplica: actualiza la misma fila
    assert again.severity == "critical"
    assert again.recalled is True
    assert again.reason == "segunda marca"


def test_mark_con_ref_invalido_falla(store: ReleaseStore) -> None:
    with pytest.raises(ReleaseStoreError, match=r"book/<id>/vX\.Y\.Z"):
        _mark(store, ref="v1.3.0")


def test_misma_tag_en_distintas_fuentes_son_independientes(store: ReleaseStore) -> None:
    _mark(store, severity=Severity.CRITICAL, recalled=True)
    _mark(store, source="fork-juan")

    assert store.get(REF, source=SOURCE).recalled is True  # type: ignore[union-attr]
    other = store.get(REF, source="fork-juan")
    assert other is not None
    assert other.recalled is False
    assert other.severity == "normal"
    TWO_SOURCES = 2
    assert len(store.list_for(BOOK)) == TWO_SOURCES
    assert len(store.list_for(BOOK, source=SOURCE)) == 1


def test_list_for_ordena_por_semver_descendente(store: ReleaseStore) -> None:
    _mark(store, ref=f"book/{BOOK}/v1.2.0")
    _mark(store, ref=f"book/{BOOK}/v1.10.0")
    _mark(store, ref=f"book/{BOOK}/v1.3.0")
    _mark(store, ref="book/otro-book/v9.9.9")

    versions = [info.version for info in store.list_for(BOOK)]
    assert versions == ["1.10.0", "1.3.0", "1.2.0"]  # orden semver, no léxico


def test_persistencia_entre_instancias_sobre_el_mismo_fichero(tmp_path: Path) -> None:
    db_url = f"sqlite:///{tmp_path / 'releases.db'}"
    store = ReleaseStore(db_url)
    _mark(store, recalled=True)

    other = ReleaseStore(db_url)  # idempotente: create_all no toca lo existente
    fetched = other.get(REF, source=SOURCE)
    assert fetched is not None
    assert fetched.recalled is True


def test_auditoria_registra_y_lista(store: ReleaseStore) -> None:
    store.record_event(
        "release.mark",
        actor="coordinator",
        source=SOURCE,
        book_id=BOOK,
        version="1.3.0",
        detail={"ref": REF, "recalled": True},
    )
    store.record_event("webhook.git", actor="git-platform", detail={"event": "push"})
    store.record_event(
        "deploy",
        actor="profesor-a",
        source=SOURCE,
        book_id=BOOK,
        version="1.0.0",
        detail={"success": True},
    )

    events = store.audit()
    assert [event.event_type for event in events] == ["deploy", "webhook.git", "release.mark"]
    by_book = store.audit(book_id=BOOK)
    assert {event.event_type for event in by_book} == {"deploy", "release.mark"}
    assert all(event.book_id == BOOK for event in by_book)
    mark = next(event for event in events if event.event_type == "release.mark")
    assert mark.actor == "coordinator"
    assert mark.detail["ref"] == REF
    assert store.audit(limit=2)[0].event_type == "deploy"


@pytest.fixture()
def deployment(
    git_repo: Path, tmp_path: Path
) -> tuple[DeploymentService, FakeMoodleProvider, ReleaseStore]:
    fake = FakeMoodleProvider(course_ids=(COURSE,))
    store = ReleaseStore(f"sqlite:///{tmp_path / 'engine.db'}")
    port = SqlReleasePort(store, source=SOURCE)
    service = DeploymentService(LocalGitProvider(git_repo), fake, port, source=SOURCE)
    return service, fake, store


def test_port_sql_bloquea_recall_en_el_planner(
    deployment: tuple[DeploymentService, FakeMoodleProvider, ReleaseStore],
) -> None:
    service, fake, store = deployment
    service.deploy(COURSE, BOOK, version="1.0.0", assume_yes=True)
    _mark(store, ref=f"book/{BOOK}/v1.0.0", recalled=True, reason="error grave")

    port = SqlReleasePort(store, source=SOURCE)
    assert port.is_recalled(SOURCE, BOOK, SemVer.parse("1.0.0"))
    with pytest.raises(RecalledVersionError, match="RECALLED"):
        service.deploy(COURSE, BOOK, version="1.0.0", assume_yes=True)

    # Drift manual para que el redeploy forzado tenga acciones (y su warning).
    record = fake.get_deploy(COURSE, SOURCE, BOOK)
    assert record is not None
    fake.mutate_chapter(record.bookid, "model", "<h1>Model EDITADO A MANO</h1>")
    result = service.deploy(COURSE, BOOK, version="1.0.0", assume_yes=True, force=True)
    assert result.success
    assert any("RECALLED" in warning for warning in result.warnings)
    assert fake.get_deploy(COURSE, SOURCE, BOOK) is not None


def test_port_sql_alimenta_el_badge_critico_del_estado(
    deployment: tuple[DeploymentService, FakeMoodleProvider, ReleaseStore],
) -> None:
    service, _fake, store = deployment
    service.deploy(COURSE, BOOK, version="1.0.0", assume_yes=True)
    # §11: el curso YA TIENE la 1.0.0 marcada critical → aviso crítico aunque
    # la última versión (1.2.0) no esté marcada.
    _mark(store, ref=f"book/{BOOK}/v1.0.0", severity=Severity.CRITICAL)

    rows = service.course_status(COURSE)

    assert len(rows) == 1
    assert rows[0].state.state is DeploymentState.UPDATE_AVAILABLE
    assert rows[0].state.severity is Severity.CRITICAL
    assert rows[0].state.version == SemVer.parse("1.0.0")


def test_deploys_quedan_en_auditoria(
    deployment: tuple[DeploymentService, FakeMoodleProvider, ReleaseStore],
) -> None:
    service, _fake, store = deployment
    service.deploy(COURSE, BOOK, version="1.0.0", assume_yes=True, deployed_by="profesor-a")

    events = store.audit(book_id=BOOK)
    deploys = [event for event in events if event.event_type == "deploy"]
    assert len(deploys) == 1
    assert deploys[0].actor == "profesor-a"
    assert deploys[0].version == "1.0.0"
    assert deploys[0].detail["success"] is True
