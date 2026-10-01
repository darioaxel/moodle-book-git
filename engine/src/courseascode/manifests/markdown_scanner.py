"""Escaneo ligero de Markdown: referencias a assets, enlaces y contenedores.

Usa markdown-it-py (CommonMark) solo para localizar referencias con su línea;
el renderizado completo es responsabilidad de ``content/`` (Fase 3).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from markdown_it import MarkdownIt

_MD = MarkdownIt("commonmark")

ReferenceKind = Literal["image", "link"]


@dataclass(frozen=True)
class MdReference:
    """Referencia encontrada en un documento Markdown."""

    kind: ReferenceKind
    target: str
    line: int  # 1-based


@dataclass(frozen=True)
class ContainerIssue:
    """Contenedor de admonition (```:::```) sin cerrar."""

    line: int  # 1-based, línea de apertura sin pareja


def scan_markdown(text: str) -> tuple[list[MdReference], list[ContainerIssue]]:
    """Extrae imágenes/enlaces (con línea) y detecta contenedores sin cerrar."""
    references: list[MdReference] = []
    for token in _MD.parse(text):
        if token.type != "inline" or token.map is None:
            continue
        line = token.map[0] + 1
        for child in token.children or []:
            if child.type == "image":
                src = child.attrGet("src")
                if isinstance(src, str) and src:
                    references.append(MdReference("image", src, line))
            elif child.type == "link_open":
                href = child.attrGet("href")
                if isinstance(href, str) and href:
                    references.append(MdReference("link", href, line))

    container_issues: list[ContainerIssue] = []
    open_line: int | None = None
    for number, raw in enumerate(text.splitlines(), start=1):
        stripped = raw.strip()
        if stripped.startswith(":::"):
            open_line = number if open_line is None else None
    if open_line is not None:
        container_issues.append(ContainerIssue(open_line))
    return references, container_issues
