"""Modelos del catálogo derivado del repo (ENG-050, §12.2).

El catálogo no tiene ``catalog.yml`` propio: cada ``CatalogEntry`` se deriva
del ``book.yml`` del último tag de su Book, y las versiones son los tags
``book/<id>/vX.Y.Z`` (ENG-051: nunca HEAD).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from courseascode.domain.semver import SemVer


class CatalogVersion(BaseModel):
    """Versión taggeada de un Book: el tag Git completo y su SemVer.

    ``version`` serializa como string (p. ej. ``"1.2.0"``) en JSON.
    """

    model_config = ConfigDict(frozen=True)

    tag: str = Field(min_length=1, description="Tag Git, p. ej. book/ut03-mvc/v1.2.0")
    version: SemVer


class CatalogEntry(BaseModel):
    """Entrada de catálogo de un Book (metadatos leídos en su último tag).

    ``versions`` está ordenada ascendentemente por SemVer y ``latest`` es la
    versión de la última (la que la UI muestra como "Última versión", §12.2).
    """

    model_config = ConfigDict(frozen=True)

    id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    type: str = Field(min_length=1)
    summary: str = ""
    description: str = ""
    tags: tuple[str, ...] = ()
    audience: str = ""
    cover: str | None = None
    chapter_count: int = Field(ge=0, description="Nº de capítulos del book.yml del último tag")
    versions: tuple[CatalogVersion, ...]
    latest: str = Field(min_length=1, description="Versión SemVer (string) más reciente")


class Catalog(BaseModel):
    """Catálogo completo de una fuente (namespace, p. ej. ``dwes``)."""

    model_config = ConfigDict(frozen=True)

    source: str = Field(min_length=1)
    books: tuple[CatalogEntry, ...] = ()


class CatalogIndex(BaseModel):
    """Índice de catálogo: fuentes visibles para un llamante concreto (ENG-053)."""

    model_config = ConfigDict(frozen=True)

    caller: str = Field(
        min_length=1, description="Identidad del llamante (header X-CourseAsCode-User)"
    )
    sources: tuple[Catalog, ...] = ()
