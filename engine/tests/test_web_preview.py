"""Tests de la preview web (ENG-040/041/043/044, §13)."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import pytest
import uvicorn
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from courseascode.cli.main import app as cli_app
from courseascode.git import LocalGitProvider
from courseascode.web import create_app

runner = CliRunner()

FIXTURES = Path(__file__).parent / "fixtures" / "repos"

VALID_REPO = FIXTURES / "valid"
V1_TAG = "book/ut03-mvc/v1.0.0"
V2_TAG = "book/ut03-mvc/v1.2.0"

HTTP_OK = 200
HTTP_NOT_FOUND = 404
HTTP_REDIRECT = 307
EXIT_USAGE = 2
DEFAULT_PORT = 3000
CUSTOM_PORT = 4173


@pytest.fixture()
def wt_client() -> TestClient:
    """App sobre el repo válido sin Git (solo working tree)."""
    return TestClient(create_app(VALID_REPO))


@pytest.fixture()
def git_client(git_repo: Path) -> TestClient:
    """App sobre el repo Git del fixture (working tree + refs)."""
    provider = LocalGitProvider(git_repo)
    return TestClient(create_app(git_repo, provider=provider))


def test_index_lista_books(wt_client: TestClient) -> None:
    response = wt_client.get("/")
    assert response.status_code == HTTP_OK
    assert "Desarrollo Web en Entorno Servidor" in response.text
    assert "ut03-mvc" in response.text
    assert 'href="/books/ut03-mvc/"' in response.text


def test_pagina_capitulo_contiene_html_toc_y_css(wt_client: TestClient) -> None:
    response = wt_client.get("/books/ut03-mvc/mvc")
    assert response.status_code == HTTP_OK
    # HTML renderizado del capítulo (su H1 y la imagen reescrita a la ruta servida).
    assert "MVC" in response.text
    assert 'src="/books/ut03-mvc/assets/mvc.svg"' in response.text
    # TOC con los capítulos y el actual marcado como current.
    for chapter_id in ("introduccion", "mvc", "model", "view", "controller"):
        assert f"/books/ut03-mvc/{chapter_id}" in response.text
    assert 'class="toc-current"' in response.text
    # CSS del tema embebido en la página.
    assert "--cc-text" in response.text
    # Selector de ref/tema inyectado.
    assert "preview-controls" in response.text


def test_redirect_raiz_book_al_primer_capitulo(wt_client: TestClient) -> None:
    response = wt_client.get("/books/ut03-mvc/", follow_redirects=False)
    assert response.status_code == HTTP_REDIRECT
    assert response.headers["location"].startswith("/books/ut03-mvc/introduccion")


def test_asset_servido_con_media_type(wt_client: TestClient) -> None:
    response = wt_client.get("/books/ut03-mvc/assets/ejemplo.png")
    assert response.status_code == HTTP_OK
    assert response.headers["content-type"] == "image/png"
    assert response.content == b"PNG\n"
    svg = wt_client.get("/books/ut03-mvc/assets/mvc.svg")
    assert svg.status_code == HTTP_OK
    assert svg.headers["content-type"] == "image/svg+xml"


def test_asset_path_traversal_devuelve_404(wt_client: TestClient) -> None:
    response = wt_client.get("/books/ut03-mvc/assets/%2e%2e/%2e%2e/course.yml")
    assert response.status_code == HTTP_NOT_FOUND
    deep = wt_client.get("/books/ut03-mvc/assets/sub/%2e%2e/%2e%2e/%2e%2e/course.yml")
    assert deep.status_code == HTTP_NOT_FOUND


def test_asset_inexistente_devuelve_404(wt_client: TestClient) -> None:
    response = wt_client.get("/books/ut03-mvc/assets/noexiste.png")
    assert response.status_code == HTTP_NOT_FOUND


def test_ref_renderiza_contenido_del_tag(git_client: TestClient, git_repo: Path) -> None:
    # El working tree (main) añadió "Aclaración" tras el tag v1.0.0.
    wt = git_client.get("/books/ut03-mvc/introduccion")
    assert wt.status_code == HTTP_OK
    assert "Aclaración" in wt.text
    tagged = git_client.get(f"/books/ut03-mvc/introduccion?ref={V1_TAG}")
    assert tagged.status_code == HTTP_OK
    assert "Aclaración" not in tagged.text


def test_ref_en_asset(git_client: TestClient, git_repo: Path) -> None:
    # El asset de Juan solo existe en la rama personal.
    response = git_client.get("/books/ut03-mvc/assets/juan.png?ref=juan")
    assert response.status_code == HTTP_OK
    assert response.headers["content-type"] == "image/png"
    missing = git_client.get("/books/ut03-mvc/assets/juan.png")
    assert missing.status_code == HTTP_NOT_FOUND


def test_ref_invalido_devuelve_404(git_client: TestClient) -> None:
    response = git_client.get("/books/ut03-mvc/introduccion?ref=no-existe")
    assert response.status_code == HTTP_NOT_FOUND
    assert "no-existe" in response.text


def test_capitulo_inexistente_devuelve_404(wt_client: TestClient) -> None:
    response = wt_client.get("/books/ut03-mvc/capitulo-fantasma")
    assert response.status_code == HTTP_NOT_FOUND


def test_book_inexistente_devuelve_404(wt_client: TestClient) -> None:
    assert wt_client.get("/books/ut99/introduccion").status_code == HTTP_NOT_FOUND
    assert wt_client.get("/books/ut99/assets/x.png").status_code == HTTP_NOT_FOUND


def test_tema_inexistente_devuelve_404(wt_client: TestClient) -> None:
    response = wt_client.get("/books/ut03-mvc/introduccion?theme=theme-fantasma")
    assert response.status_code == HTTP_NOT_FOUND
    assert "theme-fantasma" in response.text


def test_selector_incluye_tags_del_book(git_client: TestClient) -> None:
    response = git_client.get("/books/ut03-mvc/introduccion")
    assert response.status_code == HTTP_OK
    assert V1_TAG in response.text
    assert V2_TAG in response.text


def test_catalog_sin_ref_usa_ultima_version(git_client: TestClient) -> None:
    # latest = v1.2.0: "Más detalle" está en el capítulo model (no en la intro)
    # y la "Aclaración" de main aún no existe en el tag.
    intro = git_client.get("/catalog/dwes/ut03-mvc/preview")
    assert intro.status_code == HTTP_OK
    assert "Aclaración" not in intro.text
    model = git_client.get("/catalog/dwes/ut03-mvc/preview?chapter=model")
    assert model.status_code == HTTP_OK
    assert "Más detalle" in model.text
    assert "Nota de Juan" not in model.text


def test_catalog_con_ref_usa_esa_version(git_client: TestClient) -> None:
    response = git_client.get(f"/catalog/dwes/ut03-mvc/preview?ref={V1_TAG}")
    assert response.status_code == HTTP_OK
    assert "Más detalle" not in response.text
    # También admite elegir capítulo explícitamente.
    chapter = git_client.get(f"/catalog/dwes/ut03-mvc/preview?ref={V2_TAG}&chapter=model")
    assert chapter.status_code == HTTP_OK
    assert "Más detalle" in chapter.text


def test_catalog_book_sin_tags_y_sin_ref_404(git_client: TestClient) -> None:
    response = git_client.get("/catalog/dwes/ut05-sin-tags/preview")
    assert response.status_code == HTTP_NOT_FOUND
    assert "ut05-sin-tags" in response.text


def test_catalog_fuente_invalida_404(git_client: TestClient) -> None:
    assert git_client.get("/catalog/DWES!!/ut03-mvc/preview").status_code == HTTP_NOT_FOUND
    assert git_client.get("/catalog/DWES/ut03-mvc/preview").status_code == HTTP_NOT_FOUND


def test_recarga_en_vivo_sin_watcher(git_client: TestClient, git_repo: Path) -> None:
    # Guardar en el editor + refrescar el navegador debe bastar (DoD Fase 4).
    chapter = git_repo / "books" / "ut03-mvc" / "01-introduccion.md"
    before = git_client.get("/books/ut03-mvc/introduccion")
    assert "Edición en caliente" not in before.text
    texto = chapter.read_text(encoding="utf-8") + "\nEdición en caliente.\n"
    chapter.write_text(texto, encoding="utf-8")
    after = git_client.get("/books/ut03-mvc/introduccion")
    assert "Edición en caliente" in after.text


def test_preview_ref_fijado_por_la_app(git_repo: Path) -> None:
    # ENG-043: con --ref la app entera renderiza ese ref aunque no llegue ?ref.
    provider = LocalGitProvider(git_repo)
    client = TestClient(create_app(git_repo, provider=provider, default_ref=V1_TAG))
    response = client.get("/books/ut03-mvc/introduccion")
    assert response.status_code == HTTP_OK
    assert "Aclaración" not in response.text


def test_preview_cli_arranca_uvicorn(git_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, Any]] = []

    def fake_run(app: object, **kwargs: Any) -> None:
        calls.append(kwargs)

    monkeypatch.setattr(uvicorn, "run", fake_run)
    monkeypatch.chdir(git_repo)
    result = runner.invoke(cli_app, ["preview", "ut03-mvc", "--port", str(CUSTOM_PORT)])
    assert result.exit_code == 0, result.output
    assert f"http://localhost:{CUSTOM_PORT}/books/ut03-mvc/" in result.output
    assert len(calls) == 1
    assert calls[0]["port"] == CUSTOM_PORT


def test_preview_cli_acepta_ruta_de_directorio(
    git_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[dict[str, Any]] = []

    def fake_run(app: object, **kwargs: Any) -> None:
        calls.append(kwargs)

    monkeypatch.setattr(uvicorn, "run", fake_run)
    monkeypatch.chdir(git_repo)
    result = runner.invoke(cli_app, ["preview", "books/ut03-mvc"])
    assert result.exit_code == 0, result.output
    assert "ut03-mvc" in result.output
    assert calls[0]["port"] == DEFAULT_PORT


def test_preview_cli_book_desconocido_exit_2(
    git_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(git_repo)
    result = runner.invoke(cli_app, ["preview", "ut99-desconocido"])
    assert result.exit_code == EXIT_USAGE
    assert "no está en course.yml" in result.output


def test_preview_cli_ref_invalido_exit_2(git_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(git_repo)
    result = runner.invoke(cli_app, ["preview", "ut03-mvc", "--ref", "no-existe"])
    assert result.exit_code == EXIT_USAGE
    assert "no-existe" in result.output


def test_preview_cli_sin_course_yml_exit_2(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(cli_app, ["preview", "ut03-mvc"])
    assert result.exit_code == EXIT_USAGE
    assert "course.yml" in result.output


def test_preview_cli_repo_suelto_sin_git(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Repo de contenidos válido pero sin Git: funciona en modo working tree.
    monkeypatch.setattr(uvicorn, "run", lambda *a, **k: None)
    shutil.copytree(VALID_REPO, tmp_path / "suelto")
    monkeypatch.chdir(tmp_path / "suelto")
    result = runner.invoke(cli_app, ["preview", "ut03-mvc"])
    assert result.exit_code == 0, result.output
