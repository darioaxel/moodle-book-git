"""Diff estructurado entre dos refs (ENG-022)."""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass
from typing import Literal

ChangeStatus = Literal["added", "modified", "deleted", "renamed"]


@dataclass(frozen=True)
class FileChange:
    """Un archivo cambiado entre dos refs (ruta posix relativa a la raíz)."""

    path: str
    status: ChangeStatus


@dataclass(frozen=True)
class BookDiff:
    """Cambios de un Book clasificados en capítulos y assets (§22).

    ``chapter_files`` debe incluir los archivos de capítulo de ambas versiones
    (origen y destino) para clasificar también las eliminaciones.
    """

    added_chapters: tuple[str, ...] = ()
    modified_chapters: tuple[str, ...] = ()
    deleted_chapters: tuple[str, ...] = ()
    added_assets: tuple[str, ...] = ()
    modified_assets: tuple[str, ...] = ()
    deleted_assets: tuple[str, ...] = ()
    other: tuple[FileChange, ...] = ()

    def render(self) -> list[str]:
        """Resumen estructural estilo §22 (+ Nuevo capítulo: …)."""
        lines: list[str] = []
        for name in self.added_chapters:
            lines.append(f"+ Nuevo capítulo: {name}")
        for name in self.modified_chapters:
            lines.append(f"~ Modificado: {name}")
        for name in self.deleted_chapters:
            lines.append(f"- Eliminado: {name}")
        for name in self.added_assets:
            lines.append(f"+ Nuevo asset: {name}")
        for name in self.modified_assets:
            lines.append(f"~ Asset modificado: {name}")
        for name in self.deleted_assets:
            lines.append(f"- Asset eliminado: {name}")
        return lines


@dataclass(frozen=True)
class Diff:
    """Cambios entre ``ref_a`` y ``ref_b``."""

    ref_a: str
    ref_b: str
    changes: tuple[FileChange, ...]

    def for_book(self, book_path: str, chapter_files: Collection[str]) -> BookDiff:
        """Clasifica los cambios del Book ``book_path`` en capítulos/assets."""
        prefix = book_path.rstrip("/") + "/"
        chapter_set = set(chapter_files)
        added_ch: list[str] = []
        modified_ch: list[str] = []
        deleted_ch: list[str] = []
        added_as: list[str] = []
        modified_as: list[str] = []
        deleted_as: list[str] = []
        other: list[FileChange] = []
        for change in self.changes:
            if not change.path.startswith(prefix):
                continue
            rel = change.path[len(prefix) :]
            if rel in chapter_set:
                target = {
                    "added": added_ch,
                    "modified": modified_ch,
                    "deleted": deleted_ch,
                    "renamed": modified_ch,
                }[change.status]
                target.append(rel)
            elif rel.startswith("assets/"):
                target = {
                    "added": added_as,
                    "modified": modified_as,
                    "deleted": deleted_as,
                    "renamed": modified_as,
                }[change.status]
                target.append(rel)
            else:
                other.append(change)
        return BookDiff(
            added_chapters=tuple(added_ch),
            modified_chapters=tuple(modified_ch),
            deleted_chapters=tuple(deleted_ch),
            added_assets=tuple(added_as),
            modified_assets=tuple(modified_as),
            deleted_assets=tuple(deleted_as),
            other=tuple(other),
        )
