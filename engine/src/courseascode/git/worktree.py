"""Checkout temporal de una ref Git en worktree aislado.

Provisional para ENG-015: la Fase 2 (ENG-020/021) formalizará esto tras la
interfaz ``GitProvider``. No muta el working tree del usuario.
"""

from __future__ import annotations

import subprocess
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


class WorktreeError(RuntimeError):
    """Fallo al resolver el repo o crear el worktree temporal."""


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        msg = f"git {' '.join(args)} falló: {result.stderr.strip()}"
        raise WorktreeError(msg)
    return result.stdout.strip()


@contextmanager
def temporary_checkout(repo: Path, ref: str) -> Iterator[Path]:
    """Crea un worktree temporal con ``ref`` y lo elimina al salir.

    Args:
        repo: directorio dentro del repo Git (se resuelve la raíz real).
        ref: tag, rama o commit.
    """
    repo_root = Path(_git(repo, "rev-parse", "--show-toplevel"))
    tmp = Path(tempfile.mkdtemp(prefix="courseascode-ref-"))
    worktree_path = tmp / "checkout"
    _git(repo_root, "worktree", "add", "--detach", str(worktree_path), ref)
    try:
        yield worktree_path
    finally:
        subprocess.run(
            ["git", "-C", str(repo_root), "worktree", "remove", "--force", str(worktree_path)],
            capture_output=True,
            check=False,
        )
        tmp.rmdir()
