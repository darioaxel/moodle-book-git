"""Renderer único: Markdown (CommonMark + admonitions), temas Jinja2, link/asset resolvers."""

from courseascode.content.cache import CacheKey, RenderCache
from courseascode.content.links import (
    AssetAdapter,
    LinkAdapter,
    MoodleAssetAdapter,
    MoodleLinkAdapter,
    PreviewAssetAdapter,
    PreviewLinkAdapter,
    rewrite_html,
)
from courseascode.content.markdown import create_markdown
from courseascode.content.renderer import (
    AssetRef,
    RenderedBook,
    RenderedChapter,
    render_book,
    render_book_preview,
)
from courseascode.content.sanitize import sanitize_html
from courseascode.content.themes import Theme, TocItem, load_theme

__all__ = [
    "AssetAdapter",
    "AssetRef",
    "CacheKey",
    "LinkAdapter",
    "MoodleAssetAdapter",
    "MoodleLinkAdapter",
    "PreviewAssetAdapter",
    "PreviewLinkAdapter",
    "RenderCache",
    "RenderedBook",
    "RenderedChapter",
    "Theme",
    "TocItem",
    "create_markdown",
    "load_theme",
    "render_book",
    "render_book_preview",
    "rewrite_html",
    "sanitize_html",
]
