"""Tests de los endpoints de catálogo (ENG-053)."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from courseascode.catalog import Source, SourceRegistry
from courseascode.git import LocalGitProvider
from courseascode.web import create_app

FIXTURES = Path(__file__).parent / "fixtures" / "repos"
VALID_REPO = FIXTURES / "valid"

HTTP_OK = 200
HTTP_NOT_FOUND = 404
HTTP_UNAVAILABLE = 503

UT03_TAGS = ["book/ut03-mvc/v1.0.0", "book/ut03-mvc/v1.1.0", "book/ut03-mvc/v1.2.0"]
UT03_CHAPTER_COUNT = 6


@pytest.fixture()
def client(git_repo: Path) -> TestClient:
    provider = LocalGitProvider(git_repo)
    return TestClient(create_app(git_repo, provider=provider))


def _books(data: dict[str, Any], source: str = "dwes") -> list[dict[str, Any]]:
    catalog = next((s for s in data["sources"] if s["source"] == source), None)
    assert catalog is not None
    books: list[dict[str, Any]] = catalog["books"]
    return books


def _book(data: dict[str, Any], book_id: str) -> dict[str, Any]:
    book = next((b for b in _books(data) if b["id"] == book_id), None)
    assert book is not None
    return book


def test_catalog_devuelve_json_con_entries_y_versiones_ordenadas(
    client: TestClient,
) -> None:
    """DoD de la fase: GET /catalog devuelve el JSON del fixture completo."""
    response = client.get("/catalog")
    assert response.status_code == HTTP_OK
    assert response.headers["content-type"] == "application/json"
    data = response.json()
    assert data["caller"] == "anon"
    books = _books(data)
    assert [b["id"] for b in books] == ["ut03-mvc", "ut04-dao"]
    # ENG-051: ut05-sin-tags está en el course.yml pero no en el catálogo.
    ut03 = _book(data, "ut03-mvc")
    assert [v["tag"] for v in ut03["versions"]] == UT03_TAGS
    assert [v["version"] for v in ut03["versions"]] == ["1.0.0", "1.1.0", "1.2.0"]
    assert ut03["latest"] == "1.2.0"
    assert ut03["chapter_count"] == UT03_CHAPTER_COUNT
    assert ut03["title"] == "MVC y patrones de diseño"
    assert "MVC" in ut03["summary"]
    assert ut03["tags"] == ["php", "patrones", "arquitectura"]
    assert ut03["audience"] == "2º DAW · DWES"
    ut04 = _book(data, "ut04-dao")
    assert ut04["chapter_count"] == 1
    assert ut04["latest"] == "1.0.0"


def test_catalog_identifica_al_llamante_por_header(client: TestClient) -> None:
    response = client.get("/catalog", headers={"X-CourseAsCode-User": "pepe"})
    assert response.status_code == HTTP_OK
    assert response.json()["caller"] == "pepe"


def test_versions_devuelve_las_versiones_ordenadas(client: TestClient) -> None:
    response = client.get("/catalog/dwes/ut03-mvc/versions")
    assert response.status_code == HTTP_OK
    data = response.json()
    assert data["id"] == "ut03-mvc"
    assert [v["tag"] for v in data["versions"]] == UT03_TAGS
    assert data["latest"] == "1.2.0"


def test_versions_book_sin_tags_404(client: TestClient) -> None:
    response = client.get("/catalog/dwes/ut05-sin-tags/versions")
    assert response.status_code == HTTP_NOT_FOUND
    assert "ut05-sin-tags" in response.json()["detail"]


def test_versions_book_desconocido_404(client: TestClient) -> None:
    response = client.get("/catalog/dwes/ut99/versions")
    assert response.status_code == HTTP_NOT_FOUND


def test_fuente_invalida_o_desconocida_404(client: TestClient) -> None:
    assert client.get("/catalog/DWES!!/ut03-mvc/versions").status_code == HTTP_NOT_FOUND
    assert client.get("/catalog/otra/ut03-mvc/versions").status_code == HTTP_NOT_FOUND
    assert client.get("/catalog/otra").status_code == HTTP_NOT_FOUND


def test_fuente_privada_ajena_no_listada(git_repo: Path) -> None:
    registry = SourceRegistry(
        [
            Source(name="dwes", owner="coordinacion", visibility="equipo"),
            Source(name="juan", owner="juan", visibility="privada"),
        ]
    )
    provider = LocalGitProvider(git_repo)
    client = TestClient(create_app(git_repo, provider=provider, registry=registry))

    for_anon = client.get("/catalog").json()
    assert [s["source"] for s in for_anon["sources"]] == ["dwes"]
    for_pepe = client.get("/catalog", headers={"X-CourseAsCode-User": "pepe"}).json()
    assert [s["source"] for s in for_pepe["sources"]] == ["dwes"]
    for_juan = client.get("/catalog", headers={"X-CourseAsCode-User": "juan"}).json()
    assert [s["source"] for s in for_juan["sources"]] == ["dwes", "juan"]
    # Y la fuente privada tampoco responde sus versiones a otro llamante.
    denied = client.get("/catalog/juan/ut03-mvc/versions")
    assert denied.status_code == HTTP_NOT_FOUND


def test_catalog_sin_repo_git_503(tmp_path: Path) -> None:
    loose = tmp_path / "suelto"
    shutil.copytree(VALID_REPO, loose)
    client = TestClient(create_app(loose))
    response = client.get("/catalog")
    assert response.status_code == HTTP_UNAVAILABLE
    assert "repositorio Git" in response.json()["detail"]
    versions = client.get("/catalog/dwes/ut03-mvc/versions")
    assert versions.status_code == HTTP_UNAVAILABLE
