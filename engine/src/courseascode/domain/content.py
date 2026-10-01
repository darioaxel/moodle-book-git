"""Modelos de contenido: curso, Book y capítulo (§6 de la spec)."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class Numbering(StrEnum):
    """Opción de numeración del Book Moodle."""

    NONE = "none"
    NUMBERS = "numbers"
    BULLETS = "bullets"
    INDENTED = "indented"


class Chapter(BaseModel):
    """Capítulo de un Book. El ``id`` es estable (principio 4)."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    file: str = Field(min_length=1, description="Ruta del Markdown relativa al Book")


class Book(BaseModel):
    """Book definido por su ``book.yml``. La versión la da el tag Git, no el manifest."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    description: str = ""
    summary: str = ""
    tags: tuple[str, ...] = ()
    audience: str = ""
    cover: str | None = None
    numbering: Numbering = Numbering.NUMBERS
    chapters: tuple[Chapter, ...] = ()


class Course(BaseModel):
    """Curso según ``course.yml``. En Beta solo gestiona Books."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    books: tuple[Book, ...] = ()
