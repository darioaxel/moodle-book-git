"""Tests del content engine (ENG-030-037)."""

from __future__ import annotations

from pathlib import Path

from courseascode.content import (
    MoodleAssetAdapter,
    MoodleLinkAdapter,
    PreviewAssetAdapter,
    PreviewLinkAdapter,
    create_markdown,
    load_theme,
    render_book_preview,
    rewrite_html,
    sanitize_html,
)
from courseascode.content.themes import TocItem
from courseascode.manifests import ManifestParser
from courseascode.manifests.models import BookManifest, ChapterManifest

FIXTURES = Path(__file__).parent / "fixtures"
GOLDEN = FIXTURES / "golden"
EXPECTED_CHAPTERS = 5


def _book() -> BookManifest:
    return BookManifest(
        id="ut03-mvc",
        title="Golden",
        summary="Resumen",
        tags=("php",),
        audience="2º DAW",
        chapters=(
            ChapterManifest(id="intro", title="Intro", file="01-intro.md"),
            ChapterManifest(id="model", title="Model", file="03-model.md"),
        ),
    )


class TestMarkdownPipeline:
    def test_componentes_basicos(self) -> None:
        html = create_markdown().render("# Título\n\n**negrita** y *cursiva* y `code`\n")
        assert "<h1>Título</h1>" in html
        assert "<strong>negrita</strong>" in html
        assert "<em>cursiva</em>" in html
        assert "<code>code</code>" in html

    def test_tabla(self) -> None:
        html = create_markdown().render("| A | B |\n|---|---|\n| 1 | 2 |\n")
        assert "<table>" in html and "<th>A</th>" in html and "<td>2</td>" in html

    def test_codigo_con_pygments_inline(self) -> None:
        html = create_markdown().render('```php\n<?php echo "hola";\n```\n')
        assert 'style="color:' in html  # estilos inline, no clases
        assert "highlight" not in html  # noclasses=True: sin <span class="...">

    def test_codigo_lenguaje_desconocido_hace_fallback(self) -> None:
        html = create_markdown().render("```lenguaje-imposible\nhola\n```\n")
        assert '<code class="language-lenguaje-imposible">' in html

    def test_admonitions_cuatro_tipos(self) -> None:
        md = create_markdown()
        for kind in ("note", "warning", "tip", "important"):
            html = md.render(f":::{kind}\nContenido.\n:::\n")
            assert f"admonition admonition-{kind}" in html
            assert "</div>" in html

    def test_html_crudo_escapado(self) -> None:
        html = create_markdown().render("<script>alert(1)</script>\n")
        assert "<script>" not in html


class TestSanitize:
    def test_javascript_en_href_se_elimina(self) -> None:
        dirty = '<a href="javascript:alert(1)">x</a><img src="x" onerror="alert(1)">'
        clean = sanitize_html(dirty)
        assert "javascript:" not in clean
        assert "onerror" not in clean

    def test_script_se_elimina(self) -> None:
        clean = sanitize_html("<p>ok</p><script>alert(1)</script>")
        assert "<script>" not in clean
        assert "<p>ok</p>" in clean

    def test_estilos_inline_de_pygments_permitidos(self) -> None:
        dirty = '<span style="color: #9C6500; position: absolute">x</span>'
        clean = sanitize_html(dirty)
        assert "color: #9C6500" in clean
        assert "position" not in clean


class TestResolvers:
    def test_enlace_interno_resuelto_por_adapter(self) -> None:
        html, _ = rewrite_html(
            '<a href="03-model.md">Model</a>',
            _book(),
            PreviewLinkAdapter("/books/ut03-mvc"),
            PreviewAssetAdapter(),
        )
        assert 'href="/books/ut03-mvc/model"' in html

    def test_ancla_preserveda(self) -> None:
        html, _ = rewrite_html(
            '<a href="03-model.md#seccion">Model</a><a href="#local">ancla</a>',
            _book(),
            PreviewLinkAdapter("/books/ut03-mvc"),
            PreviewAssetAdapter(),
        )
        assert 'href="/books/ut03-mvc/model#seccion"' in html
        assert 'href="#local"' in html

    def test_enlace_interno_sin_resolver_se_deja(self) -> None:
        html, _ = rewrite_html(
            '<a href="99-otro.md">x</a>',
            _book(),
            PreviewLinkAdapter("/books/ut03-mvc"),
            PreviewAssetAdapter(),
        )
        assert 'href="99-otro.md"' in html

    def test_asset_recolectado_y_reescrito(self) -> None:
        html, assets = rewrite_html(
            '<img src="assets/mvc.svg" alt="x">',
            _book(),
            PreviewLinkAdapter("/books/ut03-mvc"),
            MoodleAssetAdapter({"assets/mvc.svg": "https://moodle/pluginfile.php/1/x.svg"}),
        )
        assert "pluginfile.php" in html
        assert assets == ["assets/mvc.svg"]

    def test_moodle_link_adapter_placeholder(self) -> None:
        adapter = MoodleLinkAdapter({"model": "https://moodle/mod/book/view.php?id=5&chapterid=9"})
        assert adapter.chapter_url("model") == "https://moodle/mod/book/view.php?id=5&chapterid=9"
        assert adapter.chapter_url("otro") == "#chapter-otro"


class TestRenderBook:
    def test_render_valido(self) -> None:
        root = FIXTURES / "repos" / "valid" / "books" / "ut03-mvc"
        book = ManifestParser(root.parent.parent).parse_book(root)
        rendered = render_book_preview(root, book, "/books/ut03-mvc")
        assert len(rendered.chapters) == EXPECTED_CHAPTERS
        assert {a.path for a in rendered.assets} == {"assets/mvc.svg", "assets/ejemplo.png"}
        mvc = rendered.chapter("mvc")
        assert mvc is not None
        assert 'href="/books/ut03-mvc/model"' in mvc.html
        assert 'src="assets/mvc.svg"' in mvc.html
        intro = rendered.chapter("introduccion")
        assert intro is not None
        assert "admonition-note" in intro.html

    def test_golden_file(self) -> None:
        """ENG-037: cualquier cambio de output rompe este test a propósito."""
        text = (GOLDEN / "components.md").read_text(encoding="utf-8")
        expected = (GOLDEN / "components.html").read_text(encoding="utf-8")
        html = create_markdown().render(text)
        html, _ = rewrite_html(
            html, _book(), PreviewLinkAdapter("/books/ut03-mvc"), PreviewAssetAdapter()
        )
        assert sanitize_html(html) == expected


class TestTheme:
    def test_theme_default_carga(self) -> None:
        theme = load_theme()
        assert theme.name == "theme-default"
        assert ".admonition-note" in theme.css
        assert "courseascode" in theme.css

    def test_preview_page_con_toc(self) -> None:
        theme = load_theme()
        items = [
            TocItem(title="Intro", url="/books/ut03-mvc/intro", current=True),
            TocItem(title="Model", url="/books/ut03-mvc/model"),
        ]
        page = theme.render_preview_page("MVC", "Intro", "<p>hola</p>", items)
        assert "<title>MVC — Intro</title>" in page
        assert 'href="/books/ut03-mvc/model"' in page
        assert 'class="toc-current"' in page
        assert "<p>hola</p>" in page

    def test_wrap_fragment(self) -> None:
        theme = load_theme()
        wrapped = theme.wrap_fragment("<p>x</p>")
        assert wrapped.startswith('<div class="courseascode theme-default">')
