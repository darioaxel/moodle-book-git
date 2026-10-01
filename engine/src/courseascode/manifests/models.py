"""Esquemas pydantic de los manifests (§6 de la spec).

- ``course.yml``: identidad del curso + lista de Books por ``id`` y ``path``.
- ``book.yml``: identidad del Book, metadatos de catálogo y capítulos.

La versión **no** vive en el manifest: la definen los tags Git (§6.2).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from courseascode.domain import Book, Chapter, Numbering


class BookRef(BaseModel):
    """Referencia a un Book desde ``course.yml``."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(min_length=1)
    path: str = Field(min_length=1, description="Ruta del directorio del Book relativa a la raíz")


class CourseManifest(BaseModel):
    """Contenido parseado de ``course.yml`` (§6.1)."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    books: tuple[BookRef, ...] = ()


class ChapterManifest(BaseModel):
    """Capítulo declarado en ``book.yml``. El ``id`` es estable (principio 4)."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    file: str = Field(
        min_length=1, description="Markdown del capítulo, relativo al directorio del Book"
    )


class BookManifest(BaseModel):
    """Contenido parseado de ``book.yml`` (§6.2).

    Los metadatos de catálogo (``summary``, ``tags``, ``audience``) son
    opcionales aquí para que el validador pueda reportarlos como categoría
    propia en vez de fallar el parseo.
    """

    model_config = ConfigDict(frozen=True, extra="ignore")

    id: str = Field(min_length=1)
    type: Literal["book"] = "book"
    title: str = Field(min_length=1)
    description: str = ""
    summary: str = ""
    tags: tuple[str, ...] = ()
    audience: str = ""
    cover: str | None = None
    numbering: Numbering = Numbering.NUMBERS
    chapters: tuple[ChapterManifest, ...] = ()

    def to_domain(self) -> Book:
        """Convierte al modelo de dominio (sin path: eso lo gestiona el parser)."""
        return Book(
            id=self.id,
            title=self.title,
            description=self.description,
            summary=self.summary,
            tags=self.tags,
            audience=self.audience,
            cover=self.cover,
            numbering=self.numbering,
            chapters=tuple(Chapter(id=c.id, title=c.title, file=c.file) for c in self.chapters),
        )
