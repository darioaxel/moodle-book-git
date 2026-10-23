"""Tests de errores de despliegue recuperables (ENG-102)."""

from __future__ import annotations

from pathlib import Path

import pytest

from courseascode.deployment.executor import DeploymentExecutionError
from courseascode.deployment.service import DeploymentService
from courseascode.deployment.state import compute_state
from courseascode.domain.deployment import DeploymentState
from courseascode.git import LocalGitProvider
from courseascode.moodle import FakeMoodleProvider
from courseascode.moodle.provider import MoodleError

COURSE = 101
SOURCE = "dwes"
BOOK = "ut03-mvc"


@pytest.fixture()
def scenario(git_repo: Path) -> tuple[DeploymentService, FakeMoodleProvider]:
    fake = FakeMoodleProvider()
    fake.add_course(COURSE, "DWES")
    service = DeploymentService(LocalGitProvider(git_repo), fake, source=SOURCE)
    return service, fake


def test_fallo_a_mitad_propaga_error_accionable_y_deja_estado_error(
    scenario: tuple[DeploymentService, FakeMoodleProvider],
) -> None:
    service, fake = scenario
    fake.fail_next("upsert_chapter")
    with pytest.raises(DeploymentExecutionError, match="idempotente") as excinfo:
        service.deploy(COURSE, BOOK, version="1.0.0", assume_yes=True)
    assert "relanza el mismo deploy" in str(excinfo.value)

    state = compute_state(fake, None, COURSE, SOURCE, BOOK)
    assert state.state is DeploymentState.ERROR


def test_relanzar_el_mismo_deploy_recupera_sin_duplicar(
    scenario: tuple[DeploymentService, FakeMoodleProvider],
) -> None:
    service, fake = scenario
    fake.fail_next("upsert_chapter")
    with pytest.raises(DeploymentExecutionError):
        service.deploy(COURSE, BOOK, version="1.0.0", assume_yes=True)

    result = service.deploy(COURSE, BOOK, version="1.0.0", assume_yes=True)
    assert result.success
    state = compute_state(fake, None, COURSE, SOURCE, BOOK)
    assert state.state is DeploymentState.UP_TO_DATE

    record = fake.get_deploy(COURSE, SOURCE, BOOK)
    assert record is not None
    book = fake.get_book(record.bookid)
    assert book is not None
    # Ningún capítulo duplicado pese al intento fallido intermedio.
    stable_ids = list(book.chapters)
    fixture_chapters = 5  # el book del fixture tiene 5 capítulos
    assert len(stable_ids) == len(set(stable_ids)) == fixture_chapters


def test_error_en_la_subida_de_assets_no_registra_despliegue(
    scenario: tuple[DeploymentService, FakeMoodleProvider],
) -> None:
    service, fake = scenario
    fake.fail_next("upload_asset")
    with pytest.raises(MoodleError):
        service.deploy(COURSE, BOOK, version="1.0.0", assume_yes=True)
    assert fake.get_deploy(COURSE, SOURCE, BOOK) is None
