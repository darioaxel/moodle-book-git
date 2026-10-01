"""Fixtures compartidos de tests."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures" / "repos"

UT04_BOOK_YML = """\
id: ut04-dao
type: book

title: Capa de acceso a datos

description: Desc.

summary: Resumen.
tags: [php, dao]
audience: 2º DAW

numbering: numbers

chapters:
  - id: dao
    title: DAO
    file: 01-dao.md
"""

UT05_BOOK_YML = """\
id: ut05-sin-tags
type: book

title: Book sin tags

description: Desc.

summary: Resumen.
tags: [php]
audience: 2º DAW

numbering: numbers

chapters:
  - id: inicio
    title: Inicio
    file: 01-inicio.md
"""

COURSE_YML = """\
id: dwes
title: Desarrollo Web en Entorno Servidor

books:
  - id: ut03-mvc
    path: books/ut03-mvc
  - id: ut04-dao
    path: books/ut04-dao
  - id: ut05-sin-tags
    path: books/ut05-sin-tags
"""


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True)


def _commit(repo: Path, message: str) -> None:
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", message)


@pytest.fixture()
def git_repo(tmp_path: Path) -> Path:
    """Repo de contenidos con tags oficiales, rama personal y merges (ENG-026).

    Historia::

        main:  base(v1.0.0, ut04 v1.0.0) → mod 02-mvc → +06-observer(v1.1.0)
               → mod 03-model(v1.2.0) ─┬─ main: mod README → mod 01-intro
                                      └─ juan: mod 03-model → +asset juan
                                               → +07-extra   (3 commits)
    """
    repo = tmp_path / "dwes-content"
    shutil.copytree(FIXTURES / "valid", repo)

    ut04 = repo / "books" / "ut04-dao"
    ut04.mkdir(parents=True)
    (ut04 / "book.yml").write_text(UT04_BOOK_YML, encoding="utf-8")
    (ut04 / "01-dao.md").write_text("# DAO\n", encoding="utf-8")

    ut05 = repo / "books" / "ut05-sin-tags"
    ut05.mkdir(parents=True)
    (ut05 / "book.yml").write_text(UT05_BOOK_YML, encoding="utf-8")
    (ut05 / "01-inicio.md").write_text("# Inicio\n", encoding="utf-8")

    (repo / "course.yml").write_text(COURSE_YML, encoding="utf-8")
    (repo / "README.md").write_text("# dwes-content\n", encoding="utf-8")

    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test")
    _commit(repo, "base")
    _git(repo, "tag", "book/ut03-mvc/v1.0.0")
    _git(repo, "tag", "book/ut04-dao/v1.0.0")

    mvc = repo / "books" / "ut03-mvc" / "02-mvc.md"
    mvc.write_text(mvc.read_text(encoding="utf-8") + "\nDetalle extra.\n", encoding="utf-8")
    _commit(repo, "update mvc")

    book_yml = repo / "books" / "ut03-mvc" / "book.yml"
    text = book_yml.read_text(encoding="utf-8")
    text += "  - id: observer\n    title: Observer\n    file: 06-observer.md\n"
    book_yml.write_text(text, encoding="utf-8")
    (repo / "books" / "ut03-mvc" / "06-observer.md").write_text("# Observer\n", encoding="utf-8")
    _commit(repo, "add observer")
    _git(repo, "tag", "book/ut03-mvc/v1.1.0")

    model = repo / "books" / "ut03-mvc" / "03-model.md"
    model.write_text(model.read_text(encoding="utf-8") + "\nMás detalle.\n", encoding="utf-8")
    _commit(repo, "update model")
    _git(repo, "tag", "book/ut03-mvc/v1.2.0")

    # Rama personal: 3 commits propios sobre v1.2.0
    _git(repo, "checkout", "-qb", "juan")
    model.write_text(model.read_text(encoding="utf-8") + "\nNota de Juan.\n", encoding="utf-8")
    _commit(repo, "juan: matiz en model")
    (repo / "books" / "ut03-mvc" / "assets" / "juan.png").write_bytes(b"PNG")
    mvc.write_text(
        mvc.read_text(encoding="utf-8") + "\n![Apunte de Juan](assets/juan.png)\n",
        encoding="utf-8",
    )
    _commit(repo, "juan: asset propio")
    text = book_yml.read_text(encoding="utf-8")
    text += "  - id: extra-juan\n    title: Extra de Juan\n    file: 07-extra.md\n"
    book_yml.write_text(text, encoding="utf-8")
    (repo / "books" / "ut03-mvc" / "07-extra.md").write_text("# Extra\n", encoding="utf-8")
    _commit(repo, "juan: capitulo propio")

    # main sigue avanzando (la rama personal se queda atrás en paralelo)
    _git(repo, "checkout", "-q", "main")
    (repo / "README.md").write_text("# dwes-content\n\nCurso DWES.\n", encoding="utf-8")
    _commit(repo, "main: readme")
    intro = repo / "books" / "ut03-mvc" / "01-introduccion.md"
    intro.write_text(intro.read_text(encoding="utf-8") + "\nAclaración.\n", encoding="utf-8")
    _commit(repo, "main: aclaración en intro")

    return repo
