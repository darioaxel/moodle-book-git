"""Tests de la caché de renders por commit (ENG-103)."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from courseascode.content.cache import RenderCache
from courseascode.content.renderer import RenderedBook
from courseascode.git import LocalGitProvider
from courseascode.web import create_app

V1_TAG = "book/ut03-mvc/v1.0.0"
HTTP_OK = 200


def test_cache_expira_por_ttl_con_reloj_inyectado() -> None:
    now = [0.0]
    cache: RenderCache[int] = RenderCache(ttl_seconds=10, max_entries=4, clock=lambda: now[0])
    cache.set(("a",), 1)
    assert cache.get(("a",)) == 1
    now[0] = 11.0
    assert cache.get(("a",)) is None
    assert len(cache) == 0


def test_cache_evicta_la_entrada_mas_antigua_al_llenarse() -> None:
    now = [0.0]
    max_entries = 2
    cache: RenderCache[int] = RenderCache(
        ttl_seconds=100, max_entries=max_entries, clock=lambda: now[0]
    )
    value_b = 2
    value_c = 3
    cache.set(("a",), 1)
    now[0] = 1.0
    cache.set(("b",), value_b)
    now[0] = 2.0
    cache.set(("c",), value_c)  # llena: evicta ("a",), la más antigua
    assert cache.get(("a",)) is None
    assert cache.get(("b",)) == value_b
    assert cache.get(("c",)) == value_c
    assert len(cache) == max_entries


def test_cache_clear_vacia_todo() -> None:
    cache: RenderCache[int] = RenderCache()
    cache.set(("a",), 1)
    cache.clear()
    assert len(cache) == 0
    assert cache.get(("a",)) is None


def test_get_or_render_produce_una_sola_vez() -> None:
    cache: RenderCache[str] = RenderCache()
    calls = 0

    def producer() -> str:
        nonlocal calls
        calls += 1
        return "html"

    assert cache.get_or_render(("k",), producer) == "html"
    assert cache.get_or_render(("k",), producer) == "html"
    assert calls == 1


def test_web_cachea_solo_tags_y_commits_no_working_tree_ni_ramas(
    git_repo: Path,
) -> None:
    now = [0.0]
    cache: RenderCache[RenderedBook] = RenderCache(
        ttl_seconds=100, max_entries=8, clock=lambda: now[0]
    )
    provider = LocalGitProvider(git_repo)
    client = TestClient(create_app(git_repo, provider=provider, cache=cache))

    tagged = client.get(f"/books/ut03-mvc/introduccion?ref={V1_TAG}")
    assert tagged.status_code == HTTP_OK
    assert len(cache) == 1

    # Segunda petición del mismo tag: sirve del cache, no crea entrada nueva.
    again = client.get(f"/books/ut03-mvc/introduccion?ref={V1_TAG}")
    assert again.status_code == HTTP_OK
    assert len(cache) == 1

    # Working tree y rama: mutables, nunca se cachean (ENG-103).
    client.get("/books/ut03-mvc/introduccion")
    client.get("/books/ut03-mvc/introduccion?ref=juan")
    assert len(cache) == 1

    # Commit explícito (inmutable): sí cachea. El sha de `juan` (distinto del
    # de v1.0.0) produce una clave nueva; pedir el sha de v1.0.0 reutilizaría
    # la entrada del tag (mismo commit → misma clave).
    other_commit = provider.get_commit("juan")
    client.get(f"/books/ut03-mvc/introduccion?ref={other_commit}")
    tag_and_commit_entries = 2  # el tag y el commit de `juan` (sha distinto)
    assert len(cache) == tag_and_commit_entries


def test_web_expira_entradas_por_ttl(git_repo: Path) -> None:
    now = [0.0]
    cache: RenderCache[RenderedBook] = RenderCache(
        ttl_seconds=10, max_entries=8, clock=lambda: now[0]
    )
    provider = LocalGitProvider(git_repo)
    client = TestClient(create_app(git_repo, provider=provider, cache=cache))

    client.get(f"/books/ut03-mvc/introduccion?ref={V1_TAG}")
    assert len(cache) == 1
    now[0] = 11.0
    client.get(f"/books/ut03-mvc/introduccion?ref={V1_TAG}")
    assert len(cache) == 1  # la entrada caducada se reemplaza, no se acumula
