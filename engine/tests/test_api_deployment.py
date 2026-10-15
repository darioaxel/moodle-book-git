"""Tests de los endpoints de despliegue (ENG-079) con el fake inyectado."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from courseascode.domain.deployment import Severity
from courseascode.git import LocalGitProvider
from courseascode.moodle import FakeMoodleProvider
from courseascode.web import create_app
from tests.deployment_factory import MemoryReleasePort

COURSE = 2026
SOURCE = "dwes"
BOOK = "ut03-mvc"

HTTP_OK = 200
HTTP_BAD_REQUEST = 400
HTTP_NOT_FOUND = 404
HTTP_CONFLICT = 409
HTTP_UNAVAILABLE = 503


@pytest.fixture()
def fake() -> FakeMoodleProvider:
    return FakeMoodleProvider(course_ids=(COURSE,))


@pytest.fixture()
def client(git_repo: Path, fake: FakeMoodleProvider) -> TestClient:
    provider = LocalGitProvider(git_repo)
    return TestClient(create_app(git_repo, provider=provider, moodle=fake))


def test_plan_no_ejecuta_el_despliegue(client: TestClient, fake: FakeMoodleProvider) -> None:
    response = client.post(
        "/deployment/plan",
        json={"course_id": COURSE, "source": SOURCE, "book_id": BOOK, "version": "1.0.0"},
    )

    assert response.status_code == HTTP_OK
    data = response.json()
    assert data["target_version"] == "1.0.0"
    assert data["current_version"] is None
    FIRST_DEPLOY_ACTIONS = 8  # book + 5 capítulos + 2 UPLOAD (assets) del fixture v1.0.0
    assert len(data["actions"]) == FIRST_DEPLOY_ACTIONS
    # Ni capítulos creados ni registro: solo efectos idempotentes (book/assets).
    assert fake.get_deploy(COURSE, SOURCE, BOOK) is None


def test_deploy_pipeline_completo(client: TestClient, fake: FakeMoodleProvider) -> None:
    response = client.post(
        "/deploy",
        json={
            "course_id": COURSE,
            "source": SOURCE,
            "book_id": BOOK,
            "version": "1.0.0",
            "confirmed_deletions": True,
        },
    )

    assert response.status_code == HTTP_OK
    data = response.json()
    assert data["success"] is True
    assert data["version"] == "1.0.0"
    record = fake.get_deploy(COURSE, SOURCE, BOOK)
    assert record is not None
    assert record.content_version == "1.0.0"
    assert fake.chapter_titles_in_order(record.bookid)[0] == "Introducción"


def test_status_not_deployed_y_up_to_date(client: TestClient, fake: FakeMoodleProvider) -> None:
    response = client.get(f"/deployment/status?course_id={COURSE}&source={SOURCE}&book_id={BOOK}")
    assert response.status_code == HTTP_OK
    assert response.json()["state"] == "NOT_DEPLOYED"

    client.post(
        "/deploy",
        json={
            "course_id": COURSE,
            "source": SOURCE,
            "book_id": BOOK,
            "version": "1.0.0",
            "confirmed_deletions": True,
        },
    )
    response = client.get(f"/deployment/status?course_id={COURSE}&source={SOURCE}&book_id={BOOK}")
    # La última versión taggeada es 1.2.0: con 1.0.0 desplegado hay update.
    assert response.json()["state"] == "UPDATE_AVAILABLE"


def test_status_drift_detectado(client: TestClient, fake: FakeMoodleProvider) -> None:
    client.post(
        "/deploy",
        json={
            "course_id": COURSE,
            "source": SOURCE,
            "book_id": BOOK,
            "version": "1.2.0",
            "confirmed_deletions": True,
        },
    )
    record = fake.get_deploy(COURSE, SOURCE, BOOK)
    assert record is not None
    fake.mutate_chapter(record.bookid, "model", "<h1>Model EDITADO</h1>")

    response = client.get(f"/deployment/status?course_id={COURSE}&source={SOURCE}&book_id={BOOK}")

    assert response.status_code == HTTP_OK
    data = response.json()
    assert data["state"] == "DRIFT_DETECTED"
    assert "model" in data["detail"]


def test_status_con_severidad_critica(git_repo: Path, fake: FakeMoodleProvider) -> None:
    releases = MemoryReleasePort(severities={(SOURCE, BOOK, "1.2.0"): Severity.CRITICAL})
    provider = LocalGitProvider(git_repo)
    client = TestClient(create_app(git_repo, provider=provider, moodle=fake, releases=releases))
    client.post(
        "/deploy",
        json={
            "course_id": COURSE,
            "source": SOURCE,
            "book_id": BOOK,
            "version": "1.0.0",
            "confirmed_deletions": True,
        },
    )

    response = client.get(f"/deployment/status?course_id={COURSE}&source={SOURCE}&book_id={BOOK}")

    data = response.json()
    assert data["state"] == "UPDATE_AVAILABLE"
    assert data["severity"] == "critical"


def test_where_localiza_la_version(client: TestClient, fake: FakeMoodleProvider) -> None:
    client.post(
        "/deploy",
        json={
            "course_id": COURSE,
            "source": SOURCE,
            "book_id": BOOK,
            "version": "1.0.0",
            "confirmed_deletions": True,
        },
    )

    response = client.get(f"/deployment/where?source={SOURCE}&book={BOOK}&version=1.0.0")

    assert response.status_code == HTTP_OK
    assert response.json() == {"courses": [COURSE]}


def test_version_recallada_devuelve_409(git_repo: Path, fake: FakeMoodleProvider) -> None:
    releases = MemoryReleasePort(recalled={(SOURCE, BOOK, "1.0.0")})
    provider = LocalGitProvider(git_repo)
    client = TestClient(create_app(git_repo, provider=provider, moodle=fake, releases=releases))

    response = client.post(
        "/deploy",
        json={"course_id": COURSE, "source": SOURCE, "book_id": BOOK, "version": "1.0.0"},
    )

    assert response.status_code == HTTP_CONFLICT
    assert "RECALLED" in response.json()["detail"]


def test_errores_de_peticion_400(client: TestClient) -> None:
    response = client.post(
        "/deployment/plan",
        json={"course_id": COURSE, "source": SOURCE, "book_id": BOOK, "version": "no-es-version"},
    )
    assert response.status_code == HTTP_BAD_REQUEST

    both = client.post(
        "/deployment/plan",
        json={
            "course_id": COURSE,
            "source": SOURCE,
            "book_id": BOOK,
            "version": "1.0.0",
            "ref": "main",
        },
    )
    assert both.status_code == HTTP_BAD_REQUEST


def test_fuente_invalida_404(client: TestClient) -> None:
    response = client.get("/deployment/where?source=DWES!!&book=ut03-mvc&version=1.0.0")
    assert response.status_code == HTTP_NOT_FOUND


def test_sin_moodle_configurado_503(git_repo: Path) -> None:
    provider = LocalGitProvider(git_repo)
    client = TestClient(create_app(git_repo, provider=provider))

    response = client.post(
        "/deploy",
        json={"course_id": COURSE, "source": SOURCE, "book_id": BOOK, "version": "1.0.0"},
    )
    assert response.status_code == HTTP_UNAVAILABLE
    assert "provider" in response.json()["detail"]

    response = client.get(f"/deployment/where?source={SOURCE}&book={BOOK}&version=1.0.0")
    assert response.status_code == HTTP_UNAVAILABLE


def test_deploy_elimina_con_confirmed_deletions(
    client: TestClient, fake: FakeMoodleProvider
) -> None:
    client.post(
        "/deploy",
        json={
            "course_id": COURSE,
            "source": SOURCE,
            "book_id": BOOK,
            "version": "1.1.0",
            "confirmed_deletions": True,
        },
    )
    record = fake.get_deploy(COURSE, SOURCE, BOOK)
    assert record is not None
    titles_before = fake.chapter_titles_in_order(record.bookid)

    # Rollback a v1.0.0 sin confirmar: observer sobrevive con aviso.
    response = client.post(
        "/deploy",
        json={"course_id": COURSE, "source": SOURCE, "book_id": BOOK, "version": "1.0.0"},
    )
    assert response.json()["warnings"]
    assert "Observer" in fake.chapter_titles_in_order(record.bookid)

    # Con confirmed_deletions: se borra.
    response = client.post(
        "/deploy",
        json={
            "course_id": COURSE,
            "source": SOURCE,
            "book_id": BOOK,
            "version": "1.0.0",
            "confirmed_deletions": True,
        },
    )
    assert response.status_code == HTTP_OK
    assert "Observer" not in fake.chapter_titles_in_order(record.bookid)
    assert len(fake.chapter_titles_in_order(record.bookid)) == len(titles_before) - 1
