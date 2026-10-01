"""CLI de courseascode (Typer). §29 de la spec."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from courseascode.git.worktree import WorktreeError, temporary_checkout
from courseascode.manifests.validator import Validator

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
            with temporary_checkout(root, ref) as checkout:
                report = Validator().validate(checkout)
        except WorktreeError as exc:
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
    _not_implemented()


@app.command()
def info(book: Annotated[str, typer.Argument(help="Ruta o ContentId del Book")]) -> None:
    """Muestra metadata, capítulos, assets y commit del Book (§29)."""
    _not_implemented()


@app.command()
def build(book: Annotated[str, typer.Argument(help="Ruta o ContentId del Book")]) -> None:
    """Renderiza el Book a disco sin desplegar (§29)."""
    _not_implemented()


@app.command()
def deploy(
    course: Annotated[str | None, typer.Option(help="Curso Moodle (idnumber o courseid)")] = None,
    book: Annotated[str | None, typer.Option(help="ContentId, p. ej. @dwes/ut03-mvc")] = None,
    version: Annotated[str | None, typer.Option(help="Versión a desplegar")] = None,
    ref: Annotated[
        str | None, typer.Option(help="Tag, rama o commit (alternativa a --version)")
    ] = None,
    yes: Annotated[bool, typer.Option("--yes", help="No pedir confirmación (CI/CD)")] = False,
) -> None:
    """Publica o sincroniza un Book con Moodle (§17)."""
    _not_implemented()


@app.command()
def status(course: Annotated[str | None, typer.Option(help="Curso Moodle")] = None) -> None:
    """Muestra el estado de despliegue de cada Book (§19, §23)."""
    _not_implemented()


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
