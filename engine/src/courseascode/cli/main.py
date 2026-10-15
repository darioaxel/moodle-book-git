"""CLI de courseascode (Typer). §29 de la spec."""

from __future__ import annotations

import os
import shutil
from html import escape
from pathlib import Path
from typing import Annotated

import typer
import uvicorn

from courseascode.catalog import SourceRegistry
from courseascode.content.renderer import render_book_preview
from courseascode.content.themes import TocItem, load_theme
from courseascode.deployment import (
    DeploymentService,
    DeploymentServiceError,
    RecalledVersionError,
)
from courseascode.domain.identity import ContentId
from courseascode.git import GitProviderError, LocalGitProvider, VersionResolver
from courseascode.manifests.errors import ManifestError
from courseascode.manifests.models import BookManifest
from courseascode.manifests.parser import ManifestParser
from courseascode.manifests.validator import Validator
from courseascode.moodle import MoodleError, MoodleRestClient
from courseascode.web import create_app

app = typer.Typer(
    name="courseascode",
    help="Moodle Course as Code — engine CLI (§29 de la especificación).",
    no_args_is_help=True,
    add_completion=False,
)

release_app = typer.Typer(help="Gestión de releases: severidad, recall y ciclo de vida (§11).")
app.add_typer(release_app, name="release")


def _not_implemented() -> None:
    """Placeholder de Fase 0: los comandos se implementan por fases."""
    typer.echo("not implemented yet", err=True)
    raise typer.Exit(code=1)


def _moodle_from_env() -> MoodleRestClient:
    """Cliente Moodle para los comandos que hablan con la plataforma.

    Lee solo ``MOODLE_URL``/``MOODLE_TOKEN``: el contenido se publica desde
    el repo local (cwd), así que ``CONTENT_REPO_URL``/``CONTENT_REPO_KEY``
    (config del servicio web, §25) no aplican aquí. Fallo claro (exit 2) si
    faltan.
    """
    url = os.environ.get("MOODLE_URL")
    token = os.environ.get("MOODLE_TOKEN")
    if not url or not token:
        typer.echo("error: define MOODLE_URL y MOODLE_TOKEN para hablar con Moodle", err=True)
        raise typer.Exit(code=2)
    return MoodleRestClient(url.rstrip("/"), token)


def _resolve_book(root: Path, book: str) -> tuple[Path, BookManifest]:
    """Resuelve un Book por ruta de directorio o por id en ``course.yml``.

    Mismo criterio que ``preview`` (ENG-054): si ``book`` es un directorio con
    ``book.yml`` se usa directamente; si no, se busca su id en el
    ``course.yml`` de ``root``.
    """
    candidate = Path(book)
    if candidate.is_dir() and (candidate / "book.yml").is_file():
        try:
            return candidate, ManifestParser(candidate).parse_book(candidate)
        except ManifestError as exc:
            typer.echo(f"error: book.yml inválido: {exc}", err=True)
            raise typer.Exit(code=2) from exc
    try:
        course = ManifestParser(root).parse_course()
    except ManifestError as exc:
        typer.echo(f"error: no se puede leer course.yml en {root}: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    book_ref = next((b for b in course.books if b.id == book), None)
    if book_ref is None:
        typer.echo(f"error: el book {book!r} no está en course.yml de {root}", err=True)
        raise typer.Exit(code=2)
    book_dir = root / book_ref.path
    try:
        return book_dir, ManifestParser(root).parse_book(book_dir)
    except ManifestError as exc:
        typer.echo(f"error: book.yml inválido en {book!r}: {exc}", err=True)
        raise typer.Exit(code=2) from exc


@app.command()
def validate(
    path: Annotated[str, typer.Argument(help="Ruta del repo de contenidos")] = ".",
    ref: Annotated[
        str | None, typer.Option(help="Validar un tag/rama/commit en vez del working tree")
    ] = None,
) -> None:
    """Valida manifests, capítulos, assets y enlaces (§20)."""
    root = Path(path).resolve()
    if ref is not None:
        try:
            provider = LocalGitProvider(root)
            with provider.checkout_ref(ref) as checkout:
                report = Validator().validate(checkout)
        except GitProviderError as exc:
            typer.echo(f"error: {exc}", err=True)
            raise typer.Exit(code=2) from exc
    else:
        report = Validator().validate(root)
    typer.echo(report.render())
    if not report.ok:
        raise typer.Exit(code=1)


@app.command()
def preview(
    book: Annotated[str, typer.Argument(help="Ruta o ContentId del Book")],
    ref: Annotated[str | None, typer.Option(help="Tag, rama o commit")] = None,
    port: Annotated[int, typer.Option(help="Puerto del servidor local")] = 3000,
) -> None:
    """Servidor de preview local con el tema propio (§13)."""
    root = Path.cwd()
    candidate = Path(book)
    if candidate.is_dir() and (candidate / "book.yml").is_file():
        try:
            book_id = ManifestParser(candidate).parse_book(candidate).id
        except ManifestError as exc:
            typer.echo(f"error: book.yml inválido: {exc}", err=True)
            raise typer.Exit(code=2) from exc
    else:
        book_id = book

    try:
        course = ManifestParser(root).parse_course()
    except ManifestError as exc:
        typer.echo(f"error: no se puede leer course.yml en {root}: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    if not any(b.id == book_id for b in course.books):
        typer.echo(f"error: el book {book_id!r} no está en course.yml de {root}", err=True)
        raise typer.Exit(code=2)

    try:
        provider = LocalGitProvider(root)
    except GitProviderError:
        provider = None
    if ref is not None:
        if provider is None:
            typer.echo(f"error: --ref requiere un repositorio Git en {root}", err=True)
            raise typer.Exit(code=2)
        try:
            provider.get_ref(ref)
        except GitProviderError as exc:
            typer.echo(f"error: {exc}", err=True)
            raise typer.Exit(code=2) from exc

    web_app = create_app(root, provider=provider, default_ref=ref)
    typer.echo(
        f"Preview de {book_id!r} en http://localhost:{port}/books/{book_id}/ (Ctrl+C para detener)"
    )
    uvicorn.run(web_app, host="127.0.0.1", port=port)


@app.command()
def info(book: Annotated[str, typer.Argument(help="Ruta o ContentId del Book")]) -> None:
    """Muestra metadata, capítulos, assets y commit del Book (§29).

    El namespace del ``ID:`` (p. ej. ``@dwes/ut03-mvc``) es de presentación:
    se toma de la fuente oficial del ``SourceRegistry`` por defecto. Sin repo
    Git se muestran los metadatos del working tree y commit/tags quedan en
    ``-``.
    """
    root = Path.cwd()
    book_dir, manifest = _resolve_book(root, book)
    rendered = render_book_preview(book_dir, manifest, book_base_url="")
    namespace = SourceRegistry.default().sources[0].name

    fields: list[tuple[str, str]] = [
        ("ID", f"@{namespace}/{manifest.id}"),
        ("Title", manifest.title),
        ("Type", manifest.type),
        ("Chapters", str(len(manifest.chapters))),
        ("Assets", str(len(rendered.assets))),
    ]
    try:
        provider = LocalGitProvider(root)
    except GitProviderError:
        provider = None
    if provider is None:
        fields.append(("Git commit", "-"))
        fields.append(("Tags", "-"))
    else:
        commit = provider.get_commit("HEAD")
        versions = VersionResolver(provider).versions_for(manifest.id)
        tags = ", ".join(f"v{semver}" for _, semver in versions)
        fields.append(("Git commit", commit[:7]))
        fields.append(("Tags", tags or "-"))
    for label, value in fields:
        typer.echo(f"{label + ':':<12} {value}")


@app.command()
def build(book: Annotated[str, typer.Argument(help="Ruta o ContentId del Book")]) -> None:
    """Renderiza el Book a disco sin desplegar (§29).

    Genera ``<content_root>/build/<book_id>/`` con ``index.html``, una página
    ``<capitulo>.html`` por capítulo (mismo renderer y tema que la preview,
    principio 5) y los assets referenciados copiados con su ruta relativa.
    """
    root = Path.cwd()
    book_dir, manifest = _resolve_book(root, book)
    theme = load_theme()
    rendered = render_book_preview(book_dir, manifest, book_base_url=".")
    out_dir = root / "build" / manifest.id
    out_dir.mkdir(parents=True, exist_ok=True)

    toc = [TocItem(title=c.title, url=f"{c.stable_id}.html") for c in rendered.chapters]
    for chapter in rendered.chapters:
        page = theme.render_preview_page(manifest.title, chapter.title, chapter.html, toc)
        (out_dir / f"{chapter.stable_id}.html").write_text(page, encoding="utf-8")
    index_content = f"<h1>{escape(manifest.title)}</h1>\n<p>{escape(manifest.description)}</p>"
    index = theme.render_preview_page(manifest.title, "Índice", index_content, toc)
    (out_dir / "index.html").write_text(index, encoding="utf-8")

    copied = 0
    for asset in rendered.assets:
        if not asset.local_path.is_file():
            continue
        dest = out_dir / asset.path
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(asset.local_path, dest)
        copied += 1
    typer.echo(f"Build generado en {out_dir} ({len(rendered.chapters)} capítulos, {copied} assets)")


@app.command()
def deploy(  # noqa: PLR0913, PLR0917 - comando Typer: una opción por flag (§29)
    course: Annotated[str | None, typer.Option(help="ID del curso Moodle (courseid)")] = None,
    book: Annotated[str | None, typer.Option(help="ContentId, p. ej. @dwes/ut03-mvc")] = None,
    version: Annotated[
        str | None, typer.Option(help="Versión a desplegar (rollback si es anterior, §18)")
    ] = None,
    ref: Annotated[
        str | None, typer.Option(help="Tag, rama o commit (alternativa a --version)")
    ] = None,
    yes: Annotated[bool, typer.Option("--yes", help="No pedir confirmación (CI/CD)")] = False,
    force: Annotated[
        bool, typer.Option("--force", help="Permite desplegar versiones RECALLED (§18)")
    ] = False,
) -> None:
    """Publica o sincroniza un Book con Moodle (§17): plan, confirmación, ejecución."""
    if course is None or book is None:
        typer.echo("error: --course y --book son obligatorios", err=True)
        raise typer.Exit(code=2)
    try:
        course_id = int(course)
    except ValueError:
        typer.echo(f"error: --course debe ser un ID numérico de curso: {course!r}", err=True)
        raise typer.Exit(code=2) from None
    try:
        content = ContentId.parse(book)
    except ValueError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=2) from exc

    root = Path.cwd()
    try:
        provider = LocalGitProvider(root)
    except GitProviderError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    service = DeploymentService(provider, _moodle_from_env(), source=content.source)

    try:
        plan = service.plan(course_id, content.id, version=version, ref=ref, force=force)
    except RecalledVersionError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    except (DeploymentServiceError, GitProviderError, MoodleError) as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=2) from exc

    typer.echo(plan.summary())
    typer.echo("")

    deletions_confirmed = False
    if plan.has_deletions and not yes:
        # §17.2: las eliminaciones piden confirmación aparte.
        deletions_confirmed = typer.confirm(
            "Este despliegue elimina capítulos del Book Moodle. ¿Continuar?", default=False
        )
        if not deletions_confirmed:
            typer.echo("Despliegue cancelado.")
            raise typer.Exit(code=0)
    if plan.actions and not yes and not typer.confirm("Continue?", default=True):
        typer.echo("Despliegue cancelado.")
        raise typer.Exit(code=0)
    if not plan.actions:
        typer.echo("Nothing to deploy: el Book ya está sincronizado con el objetivo.")
        return

    result = service.deploy(
        course_id,
        content.id,
        version=version,
        ref=ref,
        assume_yes=yes,
        confirmed_deletions=deletions_confirmed,
        force=force,
        deployed_by="cli",
    )
    typer.echo(result.message)
    for warning in result.warnings:
        typer.echo(f"⚠ {warning}")


@app.command()
def status(
    course: Annotated[str | None, typer.Option(help="ID del curso Moodle (courseid)")] = None,
) -> None:
    """Muestra el estado de despliegue de cada Book (§19, §23).

    Limitación (ENG-078): el provider Moodle no ofrece un listado global de
    cursos, así que ``--course`` es obligatorio en la práctica; dentro del
    curso se listan todas las claves ``(source, book)`` con despliegues.
    """
    if course is None:
        typer.echo(
            "error: --course es obligatorio: el provider no lista cursos globalmente (ENG-078)",
            err=True,
        )
        raise typer.Exit(code=2)
    try:
        course_id = int(course)
    except ValueError:
        typer.echo(f"error: --course debe ser un ID numérico de curso: {course!r}", err=True)
        raise typer.Exit(code=2) from None

    root = Path.cwd()
    try:
        provider = LocalGitProvider(root)
    except GitProviderError:
        provider = None  # sin repo Git no hay "última versión": solo drift/up-to-date
    service = DeploymentService(provider, _moodle_from_env())
    rows = service.course_status(course_id)
    if not rows:
        typer.echo(f"El curso {course_id} no tiene despliegues registrados.")
        return
    typer.echo(f"{'Book':<28} {'Version':<10} {'State':<18} {'Severity':<10} Commit")
    for row in rows:
        info = row.state
        severity = info.severity.value if info.severity else "-"
        version = f"{info.version}" if info.version is not None else "-"
        commit = (info.git_commit or "-")[:7]
        typer.echo(
            f"{row.content!s:<28} {version:<10} {info.state.value:<18} {severity:<10} {commit}"
        )


@app.command()
def export(course: Annotated[str, typer.Option(help="Curso Moodle")]) -> None:
    """Exporta el binding curso↔versión a deployments/<curso>.yml (§9)."""
    _not_implemented()


@release_app.command("mark")
def release_mark(
    ref: Annotated[str, typer.Argument(help="Tag del Book, p. ej. book/ut03-mvc/v1.3.0")],
    severity: Annotated[str, typer.Option(help="normal | critical")] = "normal",
    fixed_in: Annotated[str | None, typer.Option(help="Versión que corrige el problema")] = None,
    reason: Annotated[str | None, typer.Option(help="Motivo (obligatorio si es crítico)")] = None,
) -> None:
    """Marca severidad/recall de una versión publicada (§11)."""
    _not_implemented()


@release_app.command("list")
def release_list(book: Annotated[str, typer.Argument(help="ContentId del Book")]) -> None:
    """Lista releases y su estado del ciclo de vida (§11)."""
    _not_implemented()


def main() -> None:
    app()


if __name__ == "__main__":
    main()
