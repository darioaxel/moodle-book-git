"""CLI de courseascode (Typer). §29 de la spec."""

from __future__ import annotations

import os
import shutil
from html import escape
from pathlib import Path
from typing import Annotated

import structlog
import typer
import uvicorn

from courseascode.catalog import SourceRegistry
from courseascode.content.renderer import render_book_preview
from courseascode.content.themes import TocItem, load_theme
from courseascode.deployment import (
    DeploymentService,
    DeploymentServiceError,
    NullReleasePort,
    RecalledVersionError,
    ReleasePort,
    export_course,
)
from courseascode.domain.deployment import Severity
from courseascode.domain.identity import ContentId
from courseascode.git import GitProviderError, LocalGitProvider, VersionResolver
from courseascode.logging_config import configure_logging
from courseascode.manifests.errors import ManifestError
from courseascode.manifests.models import BookManifest
from courseascode.manifests.parser import ManifestParser
from courseascode.manifests.validator import Validator
from courseascode.moodle import MoodleError, MoodleRestClient
from courseascode.moodle.provider import MoodleProvider
from courseascode.releases import ReleaseStore, ReleaseStoreError, SqlReleasePort, default_db_url
from courseascode.web import create_app

app = typer.Typer(
    name="courseascode",
    help="Moodle Course as Code — engine CLI (§29 de la especificación).",
    no_args_is_help=True,
    add_completion=False,
)

release_app = typer.Typer(help="Gestión de releases: severidad, recall y ciclo de vida (§11).")
app.add_typer(release_app, name="release")


def _default_source() -> str:
    """Namespace de la fuente oficial (mismo criterio que ``info``, ENG-054)."""
    return SourceRegistry.default().sources[0].name


def _releases_from_env() -> ReleasePort:
    """Port de releases del CLI: ``SqlReleasePort`` si hay BD (``COURSEASCODE_DB``).

    Sin BD configurada, el comportamiento es el de siempre (``NullReleasePort``:
    sin severidades ni recalls). Así el circuito del DoD de Fase 8 funciona
    igual desde CLI y desde la API con la misma base de datos.
    """
    db_url = os.environ.get("COURSEASCODE_DB")
    if not db_url:
        return NullReleasePort()
    return SqlReleasePort(ReleaseStore(db_url), source=_default_source())


def _coordinator_token(token_option: str | None) -> str:
    """Exige el rol coordinador: el token de admin debe estar en el entorno.

    El operador es quien ejecuta el CLI, así que su credencial es la variable
    de entorno ``COURSEASCODE_ADMIN_TOKEN`` (§25: credenciales por entorno,
    nunca en el repositorio). ``--token`` permite sobreescribirla (p. ej. CI)
    pero debe coincidir con la configurada. Sin ella, salida clara con exit 3.
    """
    configured = os.environ.get("COURSEASCODE_ADMIN_TOKEN")
    if not configured:
        typer.echo(
            "error: esta operación requiere el rol coordinador; "
            "configura COURSEASCODE_ADMIN_TOKEN en el entorno",
            err=True,
        )
        raise typer.Exit(code=3)
    if token_option is not None and token_option != configured:
        typer.echo("error: token de coordinador incorrecto", err=True)
        raise typer.Exit(code=3)
    return configured


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
    service = DeploymentService(
        provider, _moodle_from_env(), _releases_from_env(), source=content.source
    )

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
    service = DeploymentService(provider, _moodle_from_env(), _releases_from_env())
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
def export(
    course: Annotated[str, typer.Option(help="ID del curso Moodle (courseid)")],
    output_dir: Annotated[
        str, typer.Option(help="Directorio de salida (relativo al cwd)")
    ] = "deployments",
) -> None:
    """Exporta el binding curso↔versión a deployments/<curso>.yml (§9, ENG-100).

    Vista exportable del estado de la tabla del plugin para reproducibilidad y
    auditoría: no es la fuente de verdad. El YAML es byte-estable para un
    mismo estado (re-export idempotente).
    """
    try:
        course_id = int(course)
    except ValueError:
        typer.echo(f"error: --course debe ser un ID numérico de curso: {course!r}", err=True)
        raise typer.Exit(code=2) from None
    moodle = _moodle_from_env()
    try:
        path = export_course(moodle, course_id, Path(output_dir))
    except MoodleError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    typer.echo(f"Exportado: {path.resolve()}")


@app.command()
def serve(
    host: Annotated[str, typer.Option(help="Interfaz de escucha")] = "127.0.0.1",
    port: Annotated[int, typer.Option(help="Puerto HTTP")] = 8000,
    content: Annotated[
        str, typer.Option(help="Raíz del repo de contenidos que sirve la app")
    ] = ".",
) -> None:
    """Sirve la app web del servicio: catálogo, preview y API (ENG-105).

    A diferencia de ``preview`` (herramienta del autor sobre el working tree),
    este es el **servicio** de plataforma (§25): lee su configuración del
    entorno —``MOODLE_URL``/``MOODLE_TOKEN`` (API de despliegue),
    ``COURSEASCODE_DB`` (releases/auditoría), ``COURSEASCODE_WEBHOOK_SECRET``
    (webhook) y ``COURSEASCODE_ADMIN_TOKEN`` (rol coordinador)— y sirve el
    repo de contenidos indicado con ``--content``. Es el entrypoint del
    contenedor Docker (``CMD courseascode serve``).
    """
    root = Path(content).resolve()
    moodle: MoodleProvider | None = None
    url = os.environ.get("MOODLE_URL")
    token = os.environ.get("MOODLE_TOKEN")
    if url and token:
        moodle = MoodleRestClient(url.rstrip("/"), token)
    db_url = os.environ.get("COURSEASCODE_DB")
    web_app = create_app(
        root,
        moodle=moodle,
        store=ReleaseStore(db_url) if db_url else None,
        webhook_secret=os.environ.get("COURSEASCODE_WEBHOOK_SECRET"),
        admin_token=os.environ.get("COURSEASCODE_ADMIN_TOKEN"),
    )
    typer.echo(f"courseascode sirviendo {root} en http://{host}:{port}/ (Ctrl+C para detener)")
    uvicorn.run(web_app, host=host, port=port)


@release_app.command("mark")
def release_mark(  # noqa: PLR0913, PLR0917 - comando Typer: una opción por flag (§11.1)
    ref: Annotated[str, typer.Argument(help="Tag del Book, p. ej. book/ut03-mvc/v1.3.0")],
    severity: Annotated[str, typer.Option(help="normal | critical")] = "normal",
    fixed_in: Annotated[str | None, typer.Option(help="Versión que corrige el problema")] = None,
    reason: Annotated[str | None, typer.Option(help="Motivo (obligatorio si es crítico)")] = None,
    recall: Annotated[
        bool, typer.Option("--recall", help="Retira la versión (RECALLED, §11)")
    ] = False,
    source: Annotated[str | None, typer.Option(help="Fuente del Book")] = None,
    token: Annotated[
        str | None, typer.Option(help="Token de coordinador (por defecto, env del operador)")
    ] = None,
) -> None:
    """Marca severidad/recall de una versión publicada (§11.1, ENG-091).

    Solo rol coordinador (``COURSEASCODE_ADMIN_TOKEN``). El motivo es
    obligatorio cuando la severidad es ``critical`` o se marca ``--recall``,
    como en el flujo de hotfix de la spec. Queda auditado (ENG-095).
    """
    try:
        severity_enum = Severity(severity)
    except ValueError:
        typer.echo(f"error: --severity debe ser normal o critical: {severity!r}", err=True)
        raise typer.Exit(code=2) from None
    if reason is None and (severity_enum is Severity.CRITICAL or recall):
        typer.echo(
            "error: --reason es obligatorio si la severidad es critical o se marca --recall",
            err=True,
        )
        raise typer.Exit(code=2)
    _coordinator_token(token)

    store = ReleaseStore(default_db_url())
    effective_source = source or _default_source()
    try:
        info = store.mark(
            ref,
            source=effective_source,
            severity=severity_enum,
            recalled=recall,
            fixed_in=fixed_in,
            reason=reason,
            marked_by="coordinator",
        )
    except ReleaseStoreError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    label = "RECALLED" if info.recalled else info.severity
    structlog.get_logger().info(
        "release.mark",
        ref=info.ref,
        source=info.source,
        severity=info.severity,
        recalled=info.recalled,
        fixed_in=info.fixed_in,
        marked_by=info.marked_by,
    )
    typer.echo(f"{info.ref} ({info.source}) marcado: {label}")


@release_app.command("list")
def release_list(book: Annotated[str, typer.Argument(help="ContentId o id del Book")]) -> None:
    """Lista releases y su estado del ciclo de vida (§11, ENG-091)."""
    source: str | None = None
    book_id = book
    try:
        content = ContentId.parse(book)
    except ValueError:
        pass
    else:
        source, book_id = content.source, content.id

    store = ReleaseStore(default_db_url())
    releases = store.list_for(book_id, source=source)
    if not releases:
        scope = f"@{source}/{book_id}" if source else book_id
        typer.echo(f"Sin releases marcadas para {scope}.")
        return
    typer.echo(
        f"{'Ref':<28} {'Src':<8} {'Version':<10} {'Severity':<10} "
        f"{'Recalled':<9} {'Fixed in':<10} {'By':<14} Marked at"
    )
    for info in releases:
        severity = info.severity.upper() if info.severity == "critical" else info.severity
        typer.echo(
            f"{info.ref:<28} {info.source:<8} {info.version:<10} {severity:<10} "
            f"{'yes' if info.recalled else 'no':<9} {(info.fixed_in or '-'):<10} "
            f"{info.marked_by:<14} {info.marked_at.isoformat()}"
        )


def main() -> None:
    configure_logging()
    app()


if __name__ == "__main__":
    main()
