"""Tests del catálogo derivado y del registro de fuentes (ENG-050/051/052)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from courseascode.catalog import (
    Catalog,
    CatalogBuilder,
    CatalogEntry,
    CatalogError,
    Source,
    SourceRegistry,
)
from courseascode.git import LocalGitProvider

UT04_TAGS = ["book/ut04-dao/v1.0.0"]
UT03_TAGS = ["book/ut03-mvc/v1.0.0", "book/ut03-mvc/v1.1.0", "book/ut03-mvc/v1.2.0"]
UT03_CHAPTER_COUNT = 6  # 5 iniciales + observer (tag v1.2.0)


@pytest.fixture()
def catalog(git_repo: Path) -> Catalog:
    provider = LocalGitProvider(git_repo)
    return CatalogBuilder(provider, course_root=git_repo).build("dwes")


def _entry(catalog: Catalog, book_id: str) -> CatalogEntry:
    entry = next((e for e in catalog.books if e.id == book_id), None)
    assert entry is not None
    return entry


def test_build_deriva_entradas_desde_los_tags(catalog: Catalog) -> None:
    assert catalog.source == "dwes"
    assert [e.id for e in catalog.books] == ["ut03-mvc", "ut04-dao"]


def test_book_sin_tags_no_aparece_eng051(catalog: Catalog, git_repo: Path) -> None:
    # ut05-sin-tags SÍ está en el course.yml del working tree pero no en el catálogo.
    course_text = (git_repo / "course.yml").read_text(encoding="utf-8")
    assert "ut05-sin-tags" in course_text
    assert all(e.id != "ut05-sin-tags" for e in catalog.books)


def test_ut03_versiones_ordenadas_y_latest(catalog: Catalog) -> None:
    entry = _entry(catalog, "ut03-mvc")
    assert [v.tag for v in entry.versions] == UT03_TAGS
    assert [str(v.version) for v in entry.versions] == ["1.0.0", "1.1.0", "1.2.0"]
    assert entry.latest == "1.2.0"
    assert entry.chapter_count == UT03_CHAPTER_COUNT


def test_ut04_versiones(catalog: Catalog) -> None:
    entry = _entry(catalog, "ut04-dao")
    assert [v.tag for v in entry.versions] == UT04_TAGS
    assert entry.latest == "1.0.0"
    assert entry.chapter_count == 1


def test_metadatos_de_catalogo_presentes(catalog: Catalog) -> None:
    entry = _entry(catalog, "ut03-mvc")
    assert entry.title == "MVC y patrones de diseño"
    assert entry.type == "book"
    assert "MVC" in entry.summary
    assert entry.tags == ("php", "patrones", "arquitectura")
    assert entry.audience == "2º DAW · DWES"
    assert entry.cover is None


def test_capitulos_y_metadatos_proceden_del_tag_no_del_working_tree(git_repo: Path) -> None:
    # Capítulo añadido SOLO al working tree (sin commit): el catálogo no lo ve.
    book_yml = git_repo / "books" / "ut04-dao" / "book.yml"
    book_yml.write_text(
        book_yml.read_text(encoding="utf-8")
        + "  - id: fantasma\n    title: Fantasma\n    file: 02-fantasma.md\n",
        encoding="utf-8",
    )
    provider = LocalGitProvider(git_repo)
    catalog = CatalogBuilder(provider, course_root=git_repo).build("dwes")
    assert _entry(catalog, "ut04-dao").chapter_count == 1


def test_sin_course_root_se_lee_de_main(git_repo: Path) -> None:
    provider = LocalGitProvider(git_repo)
    catalog = CatalogBuilder(provider).build("dwes")
    assert [e.id for e in catalog.books] == ["ut03-mvc", "ut04-dao"]


def test_course_root_sin_course_yml_falla(tmp_path: Path, git_repo: Path) -> None:
    provider = LocalGitProvider(git_repo)
    builder = CatalogBuilder(provider, course_root=tmp_path)
    with pytest.raises(CatalogError, match=r"course\.yml"):
        builder.build("dwes")


def test_book_yml_invalido_en_tag_falla(git_repo: Path) -> None:
    # Un tag cuyo book.yml no es parseable rompe la derivación de la entrada.
    book_yml = git_repo / "books" / "ut04-dao" / "book.yml"
    book_yml.write_text("id: [", encoding="utf-8")
    _git_commit(git_repo)
    subprocess.run(
        ["git", "-C", str(git_repo), "tag", "book/ut04-dao/v1.1.0"],
        check=True,
        capture_output=True,
    )
    provider = LocalGitProvider(git_repo)
    builder = CatalogBuilder(provider, course_root=git_repo)
    with pytest.raises(CatalogError, match=r"book\.yml inválido"):
        builder.build("dwes")


def _git_commit(repo: Path) -> None:
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-qm", "rompe book.yml"],
        check=True,
        capture_output=True,
    )


# -- SourceRegistry (ENG-052) ---------------------------------------------------


def test_fuente_equipo_visible_para_cualquiera() -> None:
    registry = SourceRegistry([Source(name="dwes", owner="coordinacion", visibility="equipo")])
    assert [s.name for s in registry.list_visible("anon")] == ["dwes"]
    assert [s.name for s in registry.list_visible("pepe")] == ["dwes"]
    assert registry.is_visible("dwes", "pepe")


def test_fuente_privada_solo_visible_para_su_owner() -> None:
    registry = SourceRegistry(
        [
            Source(name="dwes", owner="coordinacion", visibility="equipo"),
            Source(name="juan", owner="juan", visibility="privada"),
        ]
    )
    assert [s.name for s in registry.list_visible("pepe")] == ["dwes"]
    assert [s.name for s in registry.list_visible("juan")] == ["dwes", "juan"]
    assert not registry.is_visible("juan", "pepe")
    assert registry.is_visible("juan", "juan")
    assert registry.get("fantasma") is None


def test_registry_default_tiene_la_fuente_oficial() -> None:
    registry = SourceRegistry.default()
    assert len(registry.sources) == 1
    source = registry.sources[0]
    assert source.name == "dwes"
    assert source.visibility == "equipo"
    assert registry.is_visible("dwes", "anon")
