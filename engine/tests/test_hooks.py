"""Tests del webhook ``POST /hooks/git`` (ENG-093) y su auditoría (ENG-095).

App completa vía ``create_app`` con store + secreto de test. Firma:
``X-CourseAsCode-Signature: sha256=<hmac-sha256 hex del body crudo>``.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from courseascode.releases import ReleaseStore
from courseascode.web import create_app

SECRET = "secreto-de-test"
OTHER_SECRET = "otro-secreto"

HTTP_OK = 200
HTTP_BAD_REQUEST = 400
HTTP_UNAUTHORIZED = 401
HTTP_UNAVAILABLE = 503

PUSH_PAYLOAD = {
    "event": "push",
    "ref": "refs/tags/book/ut03-mvc/v1.3.1",
    "repository": "dwes-content",
    "commits": [{"id": "abc123", "message": "hotfix"}],
}


def _sign(body: bytes, secret: str = SECRET) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


@pytest.fixture()
def store(tmp_path: Path) -> ReleaseStore:
    return ReleaseStore(f"sqlite:///{tmp_path / 'hooks.db'}")


@pytest.fixture()
def client(tmp_path: Path, store: ReleaseStore) -> TestClient:
    app = create_app(tmp_path, store=store, webhook_secret=SECRET)
    return TestClient(app)


def test_firma_valida_procesa_el_evento(client: TestClient, store: ReleaseStore) -> None:
    body = json.dumps(PUSH_PAYLOAD).encode()
    response = client.post(
        "/hooks/git",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-CourseAsCode-Signature": _sign(body),
        },
    )

    assert response.status_code == HTTP_OK
    data = response.json()
    assert data["received"] is True
    assert data["event"] == "push"
    assert data["action"] == "recalculate"
    # Queda en auditoría (ENG-095).
    events = store.audit()
    assert len(events) == 1
    assert events[0].event_type == "webhook.git"
    assert events[0].actor == "git-platform"
    assert events[0].detail["event"] == "push"
    assert "refs/tags/book/ut03-mvc/v1.3.1" in str(events[0].detail["ref"])


def test_firma_invalida_rechaza_sin_auditar(client: TestClient, store: ReleaseStore) -> None:
    body = json.dumps(PUSH_PAYLOAD).encode()
    response = client.post(
        "/hooks/git",
        content=body,
        headers={"X-CourseAsCode-Signature": _sign(body, OTHER_SECRET)},
    )

    assert response.status_code == HTTP_UNAUTHORIZED
    assert store.audit() == []


def test_firma_ausente_rechaza(client: TestClient, store: ReleaseStore) -> None:
    body = json.dumps(PUSH_PAYLOAD).encode()
    response = client.post("/hooks/git", content=body)

    assert response.status_code == HTTP_UNAUTHORIZED
    assert store.audit() == []


def test_formato_de_firma_prefijo_sha256(client: TestClient) -> None:
    body = json.dumps(PUSH_PAYLOAD).encode()
    digest = hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()
    # Solo con prefijo "sha256=" (estilo GitHub) se acepta.
    response = client.post("/hooks/git", content=body, headers={"X-CourseAsCode-Signature": digest})
    assert response.status_code == HTTP_UNAUTHORIZED


def test_payload_no_json_rechaza_con_400(client: TestClient, store: ReleaseStore) -> None:
    body = b"no-es-json"
    response = client.post(
        "/hooks/git",
        content=body,
        headers={"X-CourseAsCode-Signature": _sign(body)},
    )

    assert response.status_code == HTTP_BAD_REQUEST
    assert store.audit() == []


def test_evento_generico_sin_campos_conocidos(client: TestClient, store: ReleaseStore) -> None:
    body = json.dumps({"foo": "bar", "plataforma": "gitlab"}).encode()
    response = client.post(
        "/hooks/git",
        content=body,
        headers={"X-CourseAsCode-Signature": _sign(body)},
    )

    assert response.status_code == HTTP_OK
    assert response.json()["event"] == "generic"  # §27: plataforma Git aún no elegida
    events = store.audit()
    assert len(events) == 1
    assert events[0].detail["event"] == "generic"


def test_sin_secreto_configurado_el_endpoint_esta_deshabilitado(
    tmp_path: Path, store: ReleaseStore
) -> None:
    app = create_app(tmp_path, store=store, webhook_secret=None)
    client = TestClient(app)
    body = json.dumps(PUSH_PAYLOAD).encode()
    response = client.post(
        "/hooks/git",
        content=body,
        headers={"X-CourseAsCode-Signature": _sign(body)},
    )

    assert response.status_code == HTTP_UNAVAILABLE


def test_sin_store_el_endpoint_esta_deshabilitado(tmp_path: Path) -> None:
    app = create_app(tmp_path, store=None, webhook_secret=SECRET)
    client = TestClient(app)

    response = client.post("/hooks/git", content=b"{}")

    assert response.status_code == HTTP_UNAVAILABLE
