"""Pipeline Markdown único del sistema (ENG-030/031).

CommonMark + tablas (preset gfm-like) + admonitions vía plugin ``container``
(sintaxis ``:::note`` … ``:::``) + resaltado Pygments con estilos **inline**
(``noclasses=True``): el tema de Moodle no incluye el CSS de Pygments, así que
el código debe llevar su color embebido o se vería distinto en preview y
producción (principio 5: preview = producción).
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING, Any

from markdown_it import MarkdownIt
from mdit_py_plugins.container import container_plugin
from pygments import highlight as pygments_highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import get_lexer_by_name
from pygments.util import ClassNotFound

if TYPE_CHECKING:
    from markdown_it.renderer import RendererProtocol
    from markdown_it.token import Token
    from markdown_it.utils import EnvType, OptionsDict

ADMONITIONS: dict[str, str] = {
    "note": "Nota",
    "warning": "Advertencia",
    "tip": "Consejo",
    "important": "Importante",
}


def _highlight(code: str, lang: str, _attrs: Any) -> str:
    """Resalta un bloque de código; cadena vacía = fallback a escape plano."""
    try:
        lexer = get_lexer_by_name(lang)
    except ClassNotFound:
        return ""
    return pygments_highlight(code, lexer, HtmlFormatter(nowrap=True, noclasses=True))


def _admonition_render(name: str, title: str) -> Callable[..., str]:
    def render(
        self: RendererProtocol,
        tokens: Sequence[Token],
        idx: int,
        options: OptionsDict,
        env: EnvType,
    ) -> str:
        if tokens[idx].nesting == 1:
            return (
                f'<div class="admonition admonition-{name}">\n'
                f'<p class="admonition-title">{title}</p>\n'
            )
        return "</div>\n"

    return render


def create_markdown() -> MarkdownIt:
    """Construye el parser Markdown con toda la sintaxis soportada (§14.1)."""
    md = MarkdownIt("gfm-like", {"highlight": _highlight, "html": False, "linkify": False})
    for name, title in ADMONITIONS.items():
        container_plugin(md, name, render=_admonition_render(name, title))
    return md
