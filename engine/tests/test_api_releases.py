"""Tests de ``GET /releases/affected`` (ENG-094) y ``GET /audit`` (ENG-095).

App completa con Git fixture + ``FakeMoodleProvider`` + store SQLite: el
deploy se hace por la API y los afectados se consultan tras marcar la release.
El envío de la notificación Moodle es del plugin 🔌: aquí solo se verifica que
el servicio calcula curso, profesor (``deployed_by``) y severidad.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from courseascode.domain.deployment import Severity
from courseascode.git import LocalGitProvider
from courseascode.moodle import FakeMoodleProvider
from courseascode.releases import ReleaseStore
from courseascode.web import create_app

COURSE = 2026
OTHER_COURSE = 2027
SOURCE = "dwes"
BOOK = "ut03-mvc"
ADMIN_TOKEN = "token-admin-test"
WEBHOOK_SECRET = "secreto-webhook-test"

HTTP_OK = 200
HTTP_BAD_REQUEST = 400
HTTP_UNAUTHORIZED = 401
HTTP_UNAVAILABLE = 503


@pytest.fixture()
def fake() -> FakeMoodleProvider:
    return FakeMoodleProvider(course_ids=(COURSE, OTHER_COURSE))


@pytest.fixture()
def store(tmp_path: Path) -> ReleaseStore:
    return ReleaseStore(f"sqlite:///{tmp_path / 'api.db'}")


@pytest.fixture()
def client(git_repo: Path, fake: FakeMoodleProvider, store: ReleaseStore) -> TestClient:
    app = create_app(
        git_repo,
        provider=LocalGitProvider(git_repo),
        moodle=fake,
        store=store,
        admin_token=ADMIN_TOKEN,
        webhook_secret=WEBHOOK_SECRET,
    )
    return TestClient(app)


def _deploy(client: TestClient, course_id: int, version: str) -> None:
    response = client.post(
        "/deploy",
        json={
            "course_id": course_id,
            "source": SOURCE,
            "book_id": BOOK,
            "version": version,
            "confirmed_deletions": True,
        },
    )
    assert response.status_code == HTTP_OK, response.text


def _mark_critical(store: ReleaseStore, version: str, *, recall: bool) -> None:
    store.mark(
        f"book/{BOOK}/v{version}",
        source=SOURCE,
        severity=Severity.CRITICAL,
        recalled=recall,
        fixed_in="1.2.0",
        reason="SQL inseguro en el ejemplo",
        marked_by="coordinator",
    )


def test_affected_lista_cursos_con_la_version_marcada(
    client: TestClient, store: ReleaseStore
) -> None:
    _deploy(client, COURSE, "1.0.0")
    _deploy(client, OTHER_COURSE, "1.0.0")
    _deploy(client, OTHER_COURSE, "1.1.0")  # ya no está en 1.0.0: no es afectado
    _mark_critical(store, "1.0.0", recall=True)

    response = client.get(f"/releases/affected?source={SOURCE}&book={BOOK}&version=1.0.0")

    assert response.status_code == HTTP_OK
    data = response.json()
    assert data["marked"] is True
    assert data["version"] == "1.0.0"
    assert len(data["affected"]) == 1
    affected = data["affected"][0]
    assert affected["course_id"] == COURSE
    assert affected["deployed_version"] == "1.0.0"
    assert affected["deployed_by"] == "api"  # mejor proxy de "profesor" disponible
    assert affected["severity"] == "critical"
    assert affected["recalled"] is True
    assert affected["fixed_in"] == "1.2.0"
    assert affected["reason"] == "SQL inseguro en el ejemplo"


def test_affected_sin_marca_devuelve_lista_sin_severidad(client: TestClient) -> None:
    deployed = client.post(
        "/deploy",
        json={
            "course_id": COURSE,
            "source": SOURCE,
            "book_id": BOOK,
            "version": "1.0.0",
            "confirmed_deletions": True,
        },
    )
    assert deployed.status_code == HTTP_OK

    response = client.get(f"/releases/affected?source={SOURCE}&book={BOOK}&version=1.0.0")

    assert response.status_code == HTTP_OK
    data = response.json()
    assert data["marked"] is False
    assert data["affected"][0]["severity"] is None
    assert data["affected"][0]["course_id"] == COURSE


def test_affected_rechaza_version_invalida(client: TestClient) -> None:
    response = client.get(f"/releases/affected?source={SOURCE}&book={BOOK}&version=abc")

    assert response.status_code == HTTP_BAD_REQUEST


def test_affected_sin_moodle_responde_503(tmp_path: Path, store: ReleaseStore) -> None:
    app = create_app(tmp_path, store=store)
    response = TestClient(app).get(f"/releases/affected?source={SOURCE}&book={BOOK}&version=1.0.0")

    assert response.status_code == HTTP_UNAVAILABLE


def test_audit_exige_token_de_administrador(client: TestClient, store: ReleaseStore) -> None:
    _mark_critical(store, "1.0.0", recall=False)
    base = "/audit?book_id=" + BOOK

    missing = client.get(base)
    wrong = client.get(base, headers={"X-CourseAsCode-Admin-Token": "otro"})
    assert missing.status_code == HTTP_UNAUTHORIZED
    assert wrong.status_code == HTTP_UNAUTHORIZED

    ok = client.get(base, headers={"X-CourseAsCode-Admin-Token": ADMIN_TOKEN})
    assert ok.status_code == HTTP_OK
    events = ok.json()["events"]
    assert len(events) == 1
    assert events[0]["event_type"] == "release.mark"
    assert events[0]["actor"] == "coordinator"
    assert events[0]["detail"]["recalled"] is False


def test_audit_deshabilitada_sin_admin_token_configurado(
    tmp_path: Path, store: ReleaseStore
) -> None:
    app = create_app(tmp_path, store=store)
    response = TestClient(app).get("/audit")

    assert response.status_code == HTTP_UNAVAILABLE


def test_webhook_end_to_end_con_secreto_de_test(client: TestClient, store: ReleaseStore) -> None:
    """DoD ENG-093 por API: firma válida → 200 + recálculo + auditoría."""
    body = json.dumps({"event": "merge", "ref": "main", "repository": "dwes-content"}).encode()
    signature = "sha256=" + hmac.new(WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()

    response = client.post(
        "/hooks/git", content=body, headers={"X-CourseAsCode-Signature": signature}
    )

    assert response.status_code == HTTP_OK
    assert response.json()["event"] == "merge"
    events = store.audit()
    assert any(event.event_type == "webhook.git" for event in events)
