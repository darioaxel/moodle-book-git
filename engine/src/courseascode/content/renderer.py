"""API pública del renderer: ``render_book`` (ENG-036).

Renderer **único** del sistema (principio 5): preview y despliegue comparten
este pipeline; solo cambian los adapters de enlaces/assets y el destino del
HTML. La versión (``ref``) se resuelve fuera: el contenido se lee del disco,
normalmente de un worktree aislado creado con ``GitProvider.checkout_ref``.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from courseascode.content.links import (
    AssetAdapter,
    LinkAdapter,
    PreviewAssetAdapter,
    PreviewLinkAdapter,
    rewrite_html,
)
from courseascode.content.markdown import create_markdown
from courseascode.content.sanitize import sanitize_html
from courseascode.manifests.models import BookManifest


@dataclass(frozen=True)
class RenderedChapter:
    """Capítulo renderizado y sanitizado, listo para preview o Moodle."""

    stable_id: str
    title: str
    file: str
    html: str


@dataclass(frozen=True)
class AssetRef:
    """Asset referenciado por el Book, con su ruta local en el checkout."""

    path: str  # relativa al directorio del Book, posix
    local_path: Path


@dataclass(frozen=True)
class RenderedBook:
    """Resultado de renderizar un Book completo."""

    book: BookManifest
    source_path: Path  # directorio del Book en disco (p. ej. un worktree)
    chapters: tuple[RenderedChapter, ...]
    assets: tuple[AssetRef, ...]

    def chapter(self, stable_id: str) -> RenderedChapter | None:
        return next((c for c in self.chapters if c.stable_id == stable_id), None)


def render_book(
    book_dir: Path,
    book: BookManifest,
    link_adapter: LinkAdapter,
    asset_adapter: AssetAdapter,
) -> RenderedBook:
    """Renderiza todos los capítulos de un Book.

    Args:
        book_dir: directorio del Book en disco (working tree o checkout de un ref).
        book: manifest parseado (``ManifestParser.parse_book``).
        link_adapter: convierte ids de capítulo en URLs (preview o Moodle).
        asset_adapter: convierte rutas de assets en URLs (preview o Moodle).

    Returns:
        ``RenderedBook`` con el HTML por capítulo y los assets referenciados.
    """
    md = create_markdown()
    assets: dict[str, AssetRef] = {}
    chapters: list[RenderedChapter] = []

    for chapter in book.chapters:
        chapter_path = book_dir / chapter.file
        text = chapter_path.read_text(encoding="utf-8")
        html = md.render(text)
        html, referenced = rewrite_html(html, book, link_adapter, asset_adapter)
        html = sanitize_html(html)
        for rel in referenced:
            assets.setdefault(rel, AssetRef(path=rel, local_path=(book_dir / rel).resolve()))
        chapters.append(
            RenderedChapter(stable_id=chapter.id, title=chapter.title, file=chapter.file, html=html)
        )

    if book.cover is not None:
        cover = book.cover.replace("\\", "/")
        assets.setdefault(cover, AssetRef(path=cover, local_path=(book_dir / cover).resolve()))

    return RenderedBook(
        book=book,
        source_path=book_dir,
        chapters=tuple(chapters),
        assets=tuple(assets.values()),
    )


def render_book_preview(
    book_dir: Path,
    book: BookManifest,
    book_base_url: str,
) -> RenderedBook:
    """Renderiza con los adapters de preview (atajo para CLI y Fase 4)."""
    return render_book(
        book_dir=book_dir,
        book=book,
        link_adapter=PreviewLinkAdapter(book_base_url),
        asset_adapter=PreviewAssetAdapter(),
    )
