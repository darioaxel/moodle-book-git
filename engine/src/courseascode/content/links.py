"""Resolución de enlaces internos y assets (ENG-034/035, §15-§16).

El renderer emite HTML con referencias abstractas; esta capa las reescribe a
URLs concretas según el destino, a través de dos adapters:

- ``LinkAdapter``: capítulo → URL (preview local o capítulo Moodle).
- ``AssetAdapter``: asset → URL (servido local en preview o ``pluginfile.php``
  en Moodle; ver ENG-072 para la estrategia de dos pasadas del despliegue).

Nunca queda un enlace apuntando a ``03-model.md`` dentro de Moodle (§16) y las
anclas internas (``#seccion``) se preservan.
"""

from __future__ import annotations

import posixpath
from dataclasses import dataclass
from html import escape
from html.parser import HTMLParser
from typing import Protocol, runtime_checkable

from courseascode.manifests.models import BookManifest

_EXTERNAL_PREFIXES = ("http://", "https://", "mailto:", "tel:", "data:", "//")


@runtime_checkable
class LinkAdapter(Protocol):
    """Convierte el id estable de un capítulo en una URL."""

    def chapter_url(self, chapter_id: str, anchor: str | None = None) -> str:
        """URL del capítulo; ``anchor`` se preserva como fragmento."""
        ...


@runtime_checkable
class AssetAdapter(Protocol):
    """Convierte la ruta de un asset en una URL."""

    def asset_url(self, asset_path: str) -> str:
        """URL servible del asset (relativa en preview, ``pluginfile.php`` en Moodle)."""
        ...


@dataclass(frozen=True)
class PreviewLinkAdapter:
    """URLs locales de la preview web (Fase 4 sirve estas rutas)."""

    base_url: str  # p. ej. "/books/ut03-mvc"

    def chapter_url(self, chapter_id: str, anchor: str | None = None) -> str:
        url = f"{self.base_url.rstrip('/')}/{chapter_id}"
        return f"{url}#{anchor}" if anchor else url


@dataclass(frozen=True)
class PreviewAssetAdapter:
    """Assets servidos localmente por la preview (rutas relativas)."""

    base_url: str = ""

    def asset_url(self, asset_path: str) -> str:
        base = self.base_url.rstrip("/")
        return f"{base}/{asset_path}" if base else asset_path


@dataclass(frozen=True)
class MoodleLinkAdapter:
    """URLs de capítulos Moodle; usa un mapa id estable → URL (§17 paso 7).

    Los capítulos aún no creados reciben un fragmento ``#chapter-<id>``:
    la idempotencia los resolverá en la segunda pasada (ENG-072).
    """

    urls: dict[str, str]

    def chapter_url(self, chapter_id: str, anchor: str | None = None) -> str:
        url = self.urls.get(chapter_id, f"#chapter-{chapter_id}")
        return f"{url}#{anchor}" if anchor else url


@dataclass(frozen=True)
class MoodleAssetAdapter:
    """URLs ``pluginfile.php`` ya subidas; placeholder si aún no existe (ENG-072)."""

    urls: dict[str, str]

    def asset_url(self, asset_path: str) -> str:
        return self.urls.get(asset_path, f"pluginfile://{asset_path}")


def _is_external(target: str) -> bool:
    return target.startswith("#") or any(target.startswith(p) for p in _EXTERNAL_PREFIXES)


def _normalize(target: str) -> str:
    return posixpath.normpath(target).replace("\\", "/")


class _Rewriter(HTMLParser):
    """Reescribe hrefs de capítulos y srcs de assets en el HTML renderizado."""

    def __init__(
        self, book: BookManifest, link_adapter: LinkAdapter, asset_adapter: AssetAdapter
    ) -> None:
        super().__init__(convert_charrefs=True)
        self._book = book
        self._link_adapter = link_adapter
        self._asset_adapter = asset_adapter
        self._out: list[str] = []
        self.assets: list[str] = []

    def html(self) -> str:
        return "".join(self._out)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._out.append(self._render_tag(tag, attrs, self_closing=False))

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._out.append(self._render_tag(tag, attrs, self_closing=True))

    def handle_endtag(self, tag: str) -> None:
        self._out.append(f"</{tag}>")

    def handle_data(self, data: str) -> None:
        self._out.append(escape(data))

    def handle_comment(self, data: str) -> None:
        self._out.append(f"<!--{escape(data)}-->")

    def _render_tag(self, tag: str, attrs: list[tuple[str, str | None]], self_closing: bool) -> str:
        rendered = [(name, self._rewrite_attr(tag, name, value)) for name, value in attrs]
        attr_text = "".join(
            f' {name}="{escape(value, quote=True)}"' if value is not None else f" {name}"
            for name, value in rendered
        )
        return f"<{tag}{attr_text}{' />' if self_closing else '>'}"

    def _rewrite_attr(self, tag: str, name: str, value: str | None) -> str | None:
        if value is None:
            return None
        if tag == "a" and name == "href":
            return self._resolve_link(value)
        if tag == "img" and name == "src":
            return self._resolve_asset(value)
        return value

    def _resolve_link(self, href: str) -> str:
        if _is_external(href):
            return href
        path, _, anchor = href.partition("#")
        if not path.endswith(".md"):
            return href
        chapter = next(
            (c for c in self._book.chapters if _normalize(c.file) == _normalize(path)),
            None,
        )
        if chapter is None:
            return href  # validate ya lo bloquea; el renderer no falla
        return self._link_adapter.chapter_url(chapter.id, anchor or None)

    def _resolve_asset(self, src: str) -> str:
        if _is_external(src):
            return src
        normalized = _normalize(src)
        self.assets.append(normalized)
        return self._asset_adapter.asset_url(normalized)


def rewrite_html(
    html: str,
    book: BookManifest,
    link_adapter: LinkAdapter,
    asset_adapter: AssetAdapter,
) -> tuple[str, list[str]]:
    """Reescribe URLs del HTML y devuelve ``(html, assets referenciados)``.

    Los assets se devuelven normalizados, relativos al directorio del capítulo
    que los referencia (todos los capítulos viven en el directorio del Book).
    """
    rewriter = _Rewriter(book, link_adapter, asset_adapter)
    rewriter.feed(html)
    rewriter.close()
    return rewriter.html(), rewriter.assets
