"""Sanitización HTML con lista blanca explícita (ENG-032, §14.2).

El Markdown no puede ejecutar JavaScript: nada de ``<script>``, ni atributos
``on*``, ni URLs ``javascript:``. Los estilos inline permitidos son solo los
que genera Pygments (``noclasses=True``) para el resaltado de código.
"""

from __future__ import annotations

import bleach
from bleach.css_sanitizer import CSSSanitizer

ALLOWED_TAGS = [
    "p",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "ul",
    "ol",
    "li",
    "blockquote",
    "pre",
    "code",
    "table",
    "thead",
    "tbody",
    "tr",
    "th",
    "td",
    "a",
    "img",
    "hr",
    "br",
    "strong",
    "em",
    "del",
    "s",
    "div",
    "span",
]

ALLOWED_ATTRIBUTES = {
    "a": ["href", "title"],
    "img": ["src", "alt", "title"],
    "code": ["class"],
    "div": ["class"],
    "p": ["class"],
    "span": ["style"],
    "th": ["align"],
    "td": ["align"],
    "ol": ["start"],
}

ALLOWED_PROTOCOLS = ["http", "https", "mailto"]

_CSS_SANITIZER = CSSSanitizer(
    allowed_css_properties=[
        "color",
        "background-color",
        "font-weight",
        "font-style",
        "text-decoration",
    ]
)


def sanitize_html(html: str) -> str:
    """Limpia un fragmento HTML según la política permitida."""
    return str(
        bleach.clean(
            html,
            tags=ALLOWED_TAGS,
            attributes=ALLOWED_ATTRIBUTES,
            protocols=ALLOWED_PROTOCOLS,
            css_sanitizer=_CSS_SANITIZER,
            strip=True,
            strip_comments=True,
        )
    )
