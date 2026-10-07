"""App FastAPI de preview web (ENG-040/041/044, §13).

Decisión de diseño — **recarga en vivo sin watcher**: la app no usa
``watchfiles`` ni websockets. Cuando se sirve el *working tree* (caso
principal del autor en VS Code) cada petición re-renderiza el Book desde
disco, sin caché. El autor guarda el archivo, refresca el navegador y ve
el cambio: cumple el DoD de la Fase 4 ("sin reiniciar nada") sin añadir
dependencias ni procesos extra. Servir un ``?ref`` concreto también es
seguro: el contenido se lee de un worktree aislado creado por petición
y se descarta al terminar.

Otras decisiones:

- Toda la generación de HTML pasa por ``Theme.render_preview_page``; el
  selector de ref/tema se inyecta como un bloque HTML generado en este
  módulo y se antepone al ``content_html`` del capítulo, sin tocar la
  firma de ``themes.py`` (ENG-040).
- Los adapters de preview reciben ``base_url="/books/<id>"`` (enlaces) y
  ``base_url="/books/<id>/assets"`` (assets), que es la ruta que ENG-041
  sirve (ENG-042).
- ``create_app`` acepta un provider explícito para tests; si no se da,
  intenta ``LocalGitProvider`` y queda ``None`` si el contenido no es un
  repo Git (entonces ``?ref`` no está disponible y se responde 404 claro).
"""

from __future__ import annotations

import mimetypes
import re
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from html import escape
from pathlib import Path
from urllib.parse import urlencode

from fastapi import FastAPI, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from courseascode.content.links import PreviewAssetAdapter, PreviewLinkAdapter
from courseascode.content.renderer import RenderedBook, render_book
from courseascode.content.themes import Theme, TocItem, load_theme
from courseascode.git.local_provider import LocalGitProvider
from courseascode.git.provider import GitProvider, GitProviderError
from courseascode.git.versioning import VersionResolver
from courseascode.manifests.errors import ManifestError
from courseascode.manifests.models import BookManifest, ChapterManifest, CourseManifest
from courseascode.manifests.parser import ManifestParser

_DEFAULT_THEME = "theme-default"
# Temas disponibles en el selector (hoy solo el base; §14 prevé más).
_AVAILABLE_THEMES: tuple[str, ...] = ("theme-default",)
_SOURCE_RE = re.compile(r"^[a-z0-9_-]+$")


class _PreviewError(Exception):
    """Error de preview con status HTTP y mensaje claro para el usuario."""

    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


@dataclass(frozen=True)
class _PreviewContext:
    """Configuración de la app de preview."""

    content_root: Path
    provider: GitProvider | None
    default_ref: str | None  # ENG-043: ref fijado por ``courseascode preview --ref``
    default_theme: str


@dataclass(frozen=True)
class _CatalogRequest:
    """Parámetros de la petición al endpoint de catálogo (ENG-044)."""

    source: str
    book_id: str
    ref: str | None
    chapter_id: str | None
    theme_name: str | None


def create_app(
    content_root: Path,
    provider: GitProvider | None = None,
    default_ref: str | None = None,
    default_theme: str = _DEFAULT_THEME,
) -> FastAPI:
    """Crea la app de preview sobre ``content_root`` (§13).

    Args:
        content_root: raíz del repo de contenidos (working tree).
        provider: provider Git; si es ``None`` se intenta ``LocalGitProvider``
            y, si el contenido no es un repo Git, queda sin provider (solo
            working tree, sin ``?ref`` ni catálogo versionado).
        default_ref: ref fijado para toda la app (``--ref`` del CLI): cuando
            se indica, todas las páginas renderizan ese ref aunque no llegue
            ``?ref`` en la petición.
        default_theme: tema usado si la petición no trae ``?theme``.
    """
    if provider is None:
        try:
            provider = LocalGitProvider(content_root)
        except GitProviderError:
            provider = None
    ctx = _PreviewContext(
        content_root=content_root.resolve(),
        provider=provider,
        default_ref=default_ref,
        default_theme=default_theme,
    )

    app = FastAPI(title="courseascode preview", docs_url=None, redoc_url=None)

    @app.exception_handler(_PreviewError)
    async def _preview_error_handler(request: Request, exc: _PreviewError) -> HTMLResponse:
        body = (
            f"<h1>Error {exc.status_code}</h1><p>{escape(exc.detail)}</p>"
            f'<p><a href="/">Índice de books</a></p>'
        )
        return HTMLResponse(body, status_code=exc.status_code)

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        """Lista los books del repo con enlace a cada uno."""
        return _index_page(ctx)

    @app.get("/books/{book_id}/")
    def book_root(book_id: str, ref: str | None = Query(default=None)) -> Response:
        """Redirige al primer capítulo del book."""
        return _book_root_redirect(ctx, book_id, ref)

    @app.get("/books/{book_id}/assets/{asset_path:path}")
    def book_asset(
        book_id: str, asset_path: str, ref: str | None = Query(default=None)
    ) -> Response:
        """Sirve un asset del book (ENG-041), blindado contra path traversal."""
        return _serve_asset(ctx, book_id, asset_path, ref)

    @app.get("/books/{book_id}/{chapter_id}", response_class=HTMLResponse)
    def book_chapter(
        book_id: str,
        chapter_id: str,
        ref: str | None = Query(default=None),
        theme_name: str | None = Query(default=None, alias="theme"),
    ) -> str:
        """Página completa de un capítulo con TOC y selector de ref/tema."""
        return _chapter_page(ctx, book_id, chapter_id, ref, theme_name)

    @app.get("/catalog/{source}/{book_id}/preview", response_class=HTMLResponse)
    def catalog_preview(
        source: str,
        book_id: str,
        ref: str | None = Query(default=None),
        chapter_id: str | None = Query(default=None, alias="chapter"),
        theme_name: str | None = Query(default=None, alias="theme"),
    ) -> str:
        """Preview pública de una versión del book (ENG-044)."""
        return _catalog_page(
            ctx,
            _CatalogRequest(
                source=source,
                book_id=book_id,
                ref=ref,
                chapter_id=chapter_id,
                theme_name=theme_name,
            ),
        )

    return app


# -- helpers internos ---------------------------------------------------------


@contextmanager
def _root_for_ref(ctx: _PreviewContext, ref: str | None) -> Iterator[Path]:
    """Raíz de contenido a usar: working tree o checkout aislado del ref."""
    effective = ref or ctx.default_ref
    if effective is None:
        yield ctx.content_root
        return
    if ctx.provider is None:
        raise _PreviewError(404, "el contenido no es un repositorio Git: ?ref no disponible")
    try:
        with ctx.provider.checkout_ref(effective) as checkout:
            yield checkout
    except GitProviderError as exc:
        raise _PreviewError(404, f"ref no encontrado: {effective!r}") from exc


def _parse_course(root: Path) -> CourseManifest:
    try:
        return ManifestParser(root).parse_course()
    except ManifestError as exc:
        raise _PreviewError(404, f"no se puede leer course.yml: {exc}") from exc


def _find_book(root: Path, book_id: str) -> tuple[Path, BookManifest]:
    """Localiza el directorio y el manifest de un book en ``root``."""
    course = _parse_course(root)
    book_ref = next((b for b in course.books if b.id == book_id), None)
    if book_ref is None:
        raise _PreviewError(404, f"book no encontrado en course.yml: {book_id!r}")
    book_dir = root / book_ref.path
    try:
        book = ManifestParser(root).parse_book(book_dir)
    except ManifestError as exc:
        raise _PreviewError(500, f"book.yml inválido en {book_id!r}: {exc}") from exc
    return book_dir, book


def _first_chapter(book: BookManifest) -> ChapterManifest:
    if not book.chapters:
        raise _PreviewError(404, f"el book {book.id!r} no tiene capítulos")
    return book.chapters[0]


def _load_theme(name: str) -> Theme:
    try:
        return load_theme(name)
    except OSError as exc:
        raise _PreviewError(404, f"tema no encontrado: {name!r}") from exc


def _book_tags(ctx: _PreviewContext, book_id: str) -> list[str]:
    if ctx.provider is None:
        return []
    try:
        return ctx.provider.list_tags(f"book/{book_id}/v*")
    except GitProviderError:
        return []


def _render(book_dir: Path, book: BookManifest, book_id: str) -> RenderedBook:
    """Renderiza el book con los adapters de preview (ENG-042).

    Los assets se referencian en Markdown con rutas relativas al Book que ya
    incluyen su directorio (p. ej. ``assets/mvc.svg``); con ``base_url`` igual
    a ``/books/<id>`` las URLs absolutas resultantes coinciden con la ruta que
    ENG-041 sirve: ``/books/<id>/assets/...``.
    """
    return render_book(
        book_dir=book_dir,
        book=book,
        link_adapter=PreviewLinkAdapter(f"/books/{book_id}"),
        asset_adapter=PreviewAssetAdapter(f"/books/{book_id}"),
    )


def _selector_html(ctx: _PreviewContext, book_id: str, ref: str | None, theme_name: str) -> str:
    """Bloque de selector de ref/tema que se antepone al contenido (ENG-040)."""
    ref_value = escape(ref or "", quote=True)
    tag_options = "".join(
        f'<option value="{escape(tag, quote=True)}"></option>' for tag in _book_tags(ctx, book_id)
    )
    theme_options = "".join(
        f'<option value="{name}"{" selected" if name == theme_name else ""}>'
        f"{escape(name.removeprefix('theme-'))}</option>"
        for name in _AVAILABLE_THEMES
    )
    return (
        '<form class="preview-controls" method="get" action="">'
        "<fieldset><legend>Preview</legend>"
        "<label>Ref "
        f'<input type="text" name="ref" list="cc-refs" value="{ref_value}" '
        'placeholder="working tree">'
        f'<datalist id="cc-refs"><option value=""></option>{tag_options}</datalist>'
        "</label> "
        '<label>Tema <select name="theme" onchange="this.form.submit()">'
        f"{theme_options}</select></label> "
        '<button type="submit">Aplicar</button>'
        "</fieldset></form>"
    )


def _index_page(ctx: _PreviewContext) -> str:
    """Lista los books del repo con enlace a cada uno."""
    with _root_for_ref(ctx, None) as root:
        course = _parse_course(root)
        theme = _load_theme(ctx.default_theme)
        items: list[str] = []
        for book_ref in course.books:
            try:
                title = ManifestParser(root).parse_book(root / book_ref.path).title
            except ManifestError:
                title = book_ref.id
            query = "?" + urlencode({"ref": ctx.default_ref}) if ctx.default_ref else ""
            items.append(
                f'<li><a href="/books/{book_ref.id}/{query}">{escape(title)}</a>'
                f" <code>{escape(book_ref.id)}</code></li>"
            )
        content = f"<h1>{escape(course.title)}</h1>\n<ul>\n{' '.join(items)}\n</ul>"
        return theme.render_preview_page(course.title, "Índice de books", content, [])


def _book_root_redirect(ctx: _PreviewContext, book_id: str, ref: str | None) -> Response:
    """Redirige a la URL del primer capítulo del book."""
    with _root_for_ref(ctx, ref) as root:
        _, book = _find_book(root, book_id)
        first = _first_chapter(book)
        query: dict[str, str] = {}
        if ref:
            query["ref"] = ref
        suffix = "?" + urlencode(query) if query else ""
        return RedirectResponse(f"/books/{book_id}/{first.id}{suffix}", status_code=307)


def _serve_asset(ctx: _PreviewContext, book_id: str, asset_path: str, ref: str | None) -> Response:
    """Sirve un asset del book (ENG-041), blindado contra path traversal."""
    with _root_for_ref(ctx, ref) as root:
        book_dir, _ = _find_book(root, book_id)
        base = book_dir.resolve()
        candidate = (book_dir / "assets" / asset_path).resolve()
        if base != candidate and base not in candidate.parents:
            raise _PreviewError(404, f"asset fuera del book: {asset_path}")
        if not candidate.is_file():
            raise _PreviewError(404, f"asset no encontrado: {asset_path}")
        media_type, _ = mimetypes.guess_type(str(candidate))
        # Se lee dentro del checkout: FileResponse lee en lazy y el worktree
        # del ref se elimina al salir del context manager.
        data = candidate.read_bytes()
    return Response(content=data, media_type=media_type or "application/octet-stream")


def _catalog_page(ctx: _PreviewContext, request: _CatalogRequest) -> str:
    """Preview pública de una versión del book (ENG-044).

    Sin ``?ref`` se resuelve la última versión oficial taggeada del book;
    si no tiene tags, 404. El ``source`` es el namespace de la fuente
    (validado con ``^[a-z0-9_-]+$``; sin ACL todavía: eso es ENG-052/053).
    """
    if not _SOURCE_RE.match(request.source):
        raise _PreviewError(404, f"fuente inválida: {request.source!r}")
    effective_ref = request.ref or None
    if effective_ref is None:
        if ctx.provider is None:
            raise _PreviewError(404, "sin repositorio Git no se puede resolver la versión")
        latest = VersionResolver(ctx.provider).latest(request.book_id)
        if latest is None:
            raise _PreviewError(404, f"el book {request.book_id!r} no tiene versiones taggeadas")
        effective_ref = latest[0]
    with _root_for_ref(ctx, effective_ref) as root:
        _, book = _find_book(root, request.book_id)
        target = request.chapter_id or _first_chapter(book).id
    return _chapter_page(ctx, request.book_id, target, effective_ref, request.theme_name)


def _chapter_page(
    ctx: _PreviewContext,
    book_id: str,
    chapter_id: str,
    ref: str | None,
    theme_name: str | None,
) -> str:
    """Construye la página HTML completa de un capítulo."""
    theme = _load_theme(theme_name or ctx.default_theme)
    with _root_for_ref(ctx, ref) as root:
        book_dir, book = _find_book(root, book_id)
        chapter = next((c for c in book.chapters if c.id == chapter_id), None)
        if chapter is None:
            raise _PreviewError(404, f"capítulo no encontrado: {chapter_id!r}")
        rendered = _render(book_dir, book, book_id)
        rendered_chapter = rendered.chapter(chapter_id)
        assert rendered_chapter is not None  # chapter sale del mismo manifest
        query: dict[str, str] = {}
        if ref:
            query["ref"] = ref
        if theme_name:
            query["theme"] = theme_name
        suffix = "?" + urlencode(query) if query else ""
        toc = [
            TocItem(
                title=c.title,
                url=f"/books/{book_id}/{c.id}{suffix}",
                current=c.id == chapter_id,
            )
            for c in book.chapters
        ]
        content = _selector_html(ctx, book_id, ref, theme.name) + "\n" + rendered_chapter.html
        return theme.render_preview_page(book.title, chapter.title, content, toc)
