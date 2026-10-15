"""Tests del cálculo de ``DeploymentState`` (ENG-074, §19)."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from courseascode.deployment import Executor, Planner, compute_state
from courseascode.domain.content import Numbering
from courseascode.domain.deployment import DeploymentState, Severity
from courseascode.domain.semver import SemVer
from courseascode.moodle import (
    DeployRecord,
    FakeMoodleProvider,
    MoodleCourse,
    MoodleError,
    MoodleProvider,
    RemoteBook,
)
from tests.deployment_factory import MemoryReleasePort, build_book

COURSE = 101
SOURCE = "dwes"
BOOK = "ut03-mvc"

FILES = {
    "01-intro.md": "# Intro\n",
    "02-mvc.md": "# MVC\n",
    "03-model.md": "# Model\n",
}


def _deployed(tmp_path: Path, version: str = "1.0.0") -> FakeMoodleProvider:
    fake = FakeMoodleProvider(course_ids=(COURSE,))
    target = build_book(tmp_path, FILES)
    plan = Planner(fake).plan(COURSE, SOURCE, BOOK, target, SemVer.parse(version))
    Executor(fake).execute(plan)
    return fake


def _bookid(fake: FakeMoodleProvider) -> int:
    record = fake.get_deploy(COURSE, SOURCE, BOOK)
    assert record is not None
    return record.bookid


def test_not_deployed() -> None:
    fake = FakeMoodleProvider(course_ids=(COURSE,))
    info = compute_state(fake, None, COURSE, SOURCE, BOOK, SemVer.parse("1.0.0"))
    assert info.state is DeploymentState.NOT_DEPLOYED


def test_up_to_date(tmp_path: Path) -> None:
    fake = _deployed(tmp_path)
    info = compute_state(fake, None, COURSE, SOURCE, BOOK, SemVer.parse("1.0.0"))
    assert info.state is DeploymentState.UP_TO_DATE
    assert info.version == SemVer.parse("1.0.0")


def test_update_available_con_severidad(tmp_path: Path) -> None:
    fake = _deployed(tmp_path)
    releases = MemoryReleasePort(severities={(SOURCE, BOOK, "1.1.0"): Severity.CRITICAL})
    info = compute_state(fake, releases, COURSE, SOURCE, BOOK, SemVer.parse("1.1.0"))
    assert info.state is DeploymentState.UPDATE_AVAILABLE
    assert info.severity is Severity.CRITICAL
    assert info.version == SemVer.parse("1.0.0")  # desplegada sigue siendo 1.0.0


def test_update_available_sin_severidad(tmp_path: Path) -> None:
    fake = _deployed(tmp_path)
    info = compute_state(fake, None, COURSE, SOURCE, BOOK, SemVer.parse("1.1.0"))
    assert info.state is DeploymentState.UPDATE_AVAILABLE
    assert info.severity is None


def test_drift_por_edicion_manual(tmp_path: Path) -> None:
    fake = _deployed(tmp_path)
    fake.mutate_chapter(_bookid(fake), "model", "<h1>Model EDITADO A MANO</h1>")

    info = compute_state(fake, None, COURSE, SOURCE, BOOK, SemVer.parse("1.0.0"))

    assert info.state is DeploymentState.DRIFT_DETECTED
    assert "model" in info.detail


def test_drift_por_capitulo_anadido_a_mano(tmp_path: Path) -> None:
    fake = _deployed(tmp_path)
    fake.upsert_chapter(_bookid(fake), "extra", "Extra", "<h1>Extra</h1>", 4)

    info = compute_state(fake, None, COURSE, SOURCE, BOOK, SemVer.parse("1.0.0"))

    assert info.state is DeploymentState.DRIFT_DETECTED
    assert "extra" in info.detail


def test_error_cuando_get_deploy_falla() -> None:
    class _MoodleRoto(MoodleProvider):
        def get_course(self, course_id: int) -> MoodleCourse:
            raise NotImplementedError

        def get_deploy(self, courseid: int, source: str, content_id: str) -> DeployRecord | None:
            raise MoodleError("local_courseascode_get_deploy: red agotada")

        def upsert_book(self, courseid: int, name: str, intro: str, numbering: Numbering) -> int:
            raise NotImplementedError

        def upsert_chapter(
            self,
            bookid: int,
            chapter_stable_id: str,
            title: str,
            content_html: str,
            position: int,
        ) -> None:
            raise NotImplementedError

        def delete_chapter(self, bookid: int, chapter_stable_id: str) -> None:
            raise NotImplementedError

        def upload_asset(self, bookid: int, filename: str, data: bytes) -> str:
            raise NotImplementedError

        def register_deploy(self, record: DeployRecord) -> int:
            raise NotImplementedError

        def list_deploys(self, courseid: int) -> list[DeployRecord]:
            raise NotImplementedError

        def get_book(self, bookid: int) -> RemoteBook | None:
            raise NotImplementedError

        def where_deployed(self, source: str, content_id: str, version: str) -> list[int]:
            raise NotImplementedError

    info = compute_state(_MoodleRoto(), None, COURSE, SOURCE, BOOK, SemVer.parse("1.0.0"))

    assert info.state is DeploymentState.ERROR
    assert "red agotada" in info.detail


def test_state_info_es_modelo_pydantic_serializable(tmp_path: Path) -> None:
    fake = _deployed(tmp_path)
    info = compute_state(fake, None, COURSE, SOURCE, BOOK, SemVer.parse("1.0.0"))
    data = info.model_dump(mode="json")
    assert data["state"] == "UP_TO_DATE"
    assert data["version"] == "1.0.0"


def test_sin_target_no_hay_update_available(tmp_path: Path) -> None:
    fake = _deployed(tmp_path)
    info = compute_state(fake, None, COURSE, SOURCE, BOOK, None)
    assert info.state is DeploymentState.UP_TO_DATE


def test_book_eliminado_a_mano_es_drift(tmp_path: Path) -> None:
    fake = _deployed(tmp_path)
    del fake._books[_bookid(fake)]  # simula borrado manual en Moodle

    info = compute_state(fake, None, COURSE, SOURCE, BOOK, SemVer.parse("1.0.0"))

    assert info.state is DeploymentState.DRIFT_DETECTED
    assert "eliminado" in info.detail


def test_where_deployed_devuelve_cursos_con_esa_version(tmp_path: Path) -> None:
    fake = _deployed(tmp_path)
    assert fake.where_deployed(SOURCE, BOOK, "1.0.0") == [COURSE]
    assert fake.where_deployed(SOURCE, BOOK, "9.9.9") == []


def test_deploy_record_previo_con_hash_corrupto(tmp_path: Path) -> None:
    """Un registro previo corrupto no impide que el estado lo reporte como drift."""
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
            deployed_at=datetime(2026, 1, 1),
            deployed_by="tester",
        )
    )

    info = compute_state(fake, None, COURSE, SOURCE, BOOK, SemVer.parse("1.0.0"))

    assert info.state is DeploymentState.DRIFT_DETECTED
