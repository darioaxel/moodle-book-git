"""Sistema de temas: CSS + plantillas Jinja2 por tema (ENG-033)."""

from __future__ import annotations

from dataclasses import dataclass
from importlib.resources import files

from jinja2 import Template

_THEME_ROOT = "themes"
_DEFAULT_THEME = "theme-default"


@dataclass(frozen=True)
class TocItem:
    """Entrada del índice de capítulos de la preview."""

    title: str
    url: str
    current: bool = False


@dataclass(frozen=True)
class Theme:
    """Un tema: CSS inyectable + plantilla de página de preview."""

    name: str
    css: str
    _preview_template: Template

    @classmethod
    def load(cls, name: str = _DEFAULT_THEME) -> Theme:
        """Carga un tema empaquetado en ``courseascode.content.themes``."""
        base = files("courseascode.content").joinpath(_THEME_ROOT, name)
        css = base.joinpath("style.css").read_text(encoding="utf-8")
        preview_html = base.joinpath("preview.html").read_text(encoding="utf-8")
        return cls(name=name, css=css, _preview_template=Template(preview_html))

    def render_preview_page(
        self,
        book_title: str,
        chapter_title: str,
        content_html: str,
        toc: list[TocItem],
    ) -> str:
        """Página HTML completa de preview con el índice y el tema aplicado."""
        return self._preview_template.render(
            theme_name=self.name.removeprefix("theme-"),
            css=self.css,
            book_title=book_title,
            chapter_title=chapter_title,
            content=content_html,
            toc=toc,
        )

    def wrap_fragment(self, content_html: str) -> str:
        """Fragmento envuelto con el contenedor del tema (para inyectar en Moodle)."""
        theme_name = self.name.removeprefix("theme-")
        return f'<div class="courseascode theme-{theme_name}">\n{content_html}\n</div>'


def load_theme(name: str = _DEFAULT_THEME) -> Theme:
    """Atajo para cargar un tema."""
    return Theme.load(name)
