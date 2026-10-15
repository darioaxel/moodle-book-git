"""Fábricas compartidas de los tests del deployment engine (Fase 7).

Construye ``RenderedBook`` reales desde un directorio temporal y un
``ReleasePort`` en memoria con severidades/recalls de ejemplo (ENG-075).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from courseascode.content.links import MoodleAssetAdapter, MoodleLinkAdapter
from courseascode.content.renderer import RenderedBook, render_book
from courseascode.domain.deployment import Severity
from courseascode.domain.semver import SemVer
from courseascode.manifests.parser import ManifestParser

BOOK_YML = """\
id: ut03-mvc
type: book

title: MVC y patrones de diseño
description: Introducción al patrón MVC.

summary: Resumen.
tags: [php]
audience: 2º DAW
numbering: numbers

chapters:
  - id: introduccion
    title: Introducción
    file: 01-intro.md
  - id: mvc
    title: MVC
    file: 02-mvc.md
  - id: model
    title: Model
    file: 03-model.md
"""


def build_book(tmp_path: Path, files: dict[str, str], book_yml: str | None = None) -> RenderedBook:
    """Escribe ``book.yml`` + capítulos en ``tmp_path`` y renderiza el Book.

    El render usa los adapters de Moodle con mapas vacíos: los assets quedan
    con placeholder ``pluginfile://`` y los enlaces con ``#chapter-<id>``.
    """
    (tmp_path / "book.yml").parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / "book.yml").write_text(book_yml or BOOK_YML, encoding="utf-8")
    for name, text in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    book = ManifestParser(tmp_path).parse_book(tmp_path)
    return render_book(
        book_dir=tmp_path,
        book=book,
        link_adapter=MoodleLinkAdapter({}),
        asset_adapter=MoodleAssetAdapter({}),
    )


@dataclass
class MemoryReleasePort:
    """``ReleasePort`` en memoria para tests de ENG-074/ENG-075."""

    severities: dict[tuple[str, str, str], Severity] = field(default_factory=dict)
    recalled: set[tuple[str, str, str]] = field(default_factory=set)

    def severity_of(self, source: str, book_id: str, version: SemVer) -> Severity | None:
        return self.severities.get((source, book_id, str(version)))

    def is_recalled(self, source: str, book_id: str, version: SemVer) -> bool:
        return (source, book_id, str(version)) in self.recalled
