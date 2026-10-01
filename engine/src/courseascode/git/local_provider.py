"""``LocalGitProvider``: GitPython sobre un repo local (ENG-021).

Los worktrees temporales usan el CLI de Git (``git worktree add``): GitPython no
expone worktrees de forma fiable. El resto de operaciones van por la API tipada.
"""

from __future__ import annotations

import fnmatch
import subprocess
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from git import Repo
from git.exc import BadName, InvalidGitRepositoryError
from git.objects import Blob, Commit, Tree

from courseascode.domain import GitRef
from courseascode.git.diff import ChangeStatus, Diff, FileChange
from courseascode.git.provider import GitProvider, GitProviderError

_STATUS_MAP: dict[str, ChangeStatus] = {
    "A": "added",
    "M": "modified",
    "D": "deleted",
    "R": "renamed",
    "T": "modified",
}


class LocalGitProvider(GitProvider):
    """Implementación sobre un repositorio Git local."""

    def __init__(self, repo_path: Path) -> None:
        try:
            self._repo = Repo(repo_path, search_parent_directories=True)
        except InvalidGitRepositoryError as exc:
            msg = f"No es un repositorio Git: {repo_path}"
            raise GitProviderError(msg) from exc
        self._root = Path(self._repo.working_tree_dir or self._repo.git_dir)

    # -- refs y checkouts -------------------------------------------------------

    def get_ref(self, ref: str) -> GitRef:
        try:
            self._repo.commit(ref)
        except BadName as exc:
            msg = f"Referencia Git no encontrada: {ref!r}"
            raise GitProviderError(msg) from exc
        return GitRef.of(ref)

    @contextmanager
    def checkout_ref(self, ref: str) -> Iterator[Path]:
        tmp = Path(tempfile.mkdtemp(prefix="courseascode-wt-"))
        worktree_path = tmp / "checkout"
        self._git("worktree", "add", "--detach", str(worktree_path), ref)
        try:
            yield worktree_path
        finally:
            subprocess.run(
                ["git", "-C", str(self._root), "worktree", "remove", "--force", str(worktree_path)],
                capture_output=True,
                check=False,
            )
            tmp.rmdir()

    # -- contenido ---------------------------------------------------------------

    def list_files(self, ref: str, path: str = "") -> list[str]:
        commit = self._commit(ref)
        tree = commit.tree / path if path else commit.tree
        return sorted(str(item.path) for item in self._walk(tree))

    def get_file(self, ref: str, path: str) -> str:
        commit = self._commit(ref)
        try:
            entry = commit.tree / path
        except KeyError as exc:
            msg = f"Archivo no encontrado en {ref}: {path}"
            raise GitProviderError(msg) from exc
        if entry.type != "blob":
            msg = f"No es un archivo en {ref}: {path}"
            raise GitProviderError(msg)
        data: bytes = entry.data_stream.read()
        return data.decode("utf-8")

    def get_commit(self, ref: str) -> str:
        return str(self._commit(ref).hexsha)

    # -- tags y diffs --------------------------------------------------------------

    def list_tags(self, pattern: str = "*") -> list[str]:
        return sorted(tag.name for tag in self._repo.tags if fnmatch.fnmatch(tag.name, pattern))

    def diff(self, ref_a: str, ref_b: str) -> Diff:
        commit_a = self._commit(ref_a)
        commit_b = self._commit(ref_b)
        changes = []
        for item in commit_a.diff(commit_b):
            status = _STATUS_MAP.get(item.change_type or "", "modified")
            path = item.b_path or item.a_path or ""
            changes.append(FileChange(path=path, status=status))
        return Diff(ref_a=ref_a, ref_b=ref_b, changes=tuple(changes))

    def merge_base(self, ref_a: str, ref_b: str) -> str:
        bases = self._repo.merge_base(ref_a, ref_b)
        if not bases:
            msg = f"Sin ancestro común entre {ref_a!r} y {ref_b!r}"
            raise GitProviderError(msg)
        return bases[0].hexsha

    def commits_ahead(self, base: str, ref: str) -> int:
        return len(list(self._repo.iter_commits(f"{base}..{ref}")))

    def is_ancestor(self, ref_a: str, ref_b: str) -> bool:
        sha_a = self.get_commit(ref_a)
        bases = self._repo.merge_base(ref_a, ref_b)
        return bool(bases) and bases[0].hexsha == sha_a

    def current_branch(self) -> str:
        try:
            branch = self._repo.active_branch
        except TypeError as exc:
            msg = "HEAD desacoplado: no hay rama actual"
            raise GitProviderError(msg) from exc
        return str(branch)

    # -- internos ------------------------------------------------------------------

    def _commit(self, ref: str) -> Commit:
        try:
            return self._repo.commit(ref)
        except BadName as exc:
            msg = f"Referencia Git no encontrada: {ref!r}"
            raise GitProviderError(msg) from exc

    def _git(self, *args: str) -> str:
        result = subprocess.run(
            ["git", "-C", str(self._root), *args],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            msg = f"git {' '.join(args)} falló: {result.stderr.strip()}"
            raise GitProviderError(msg)
        return result.stdout.strip()

    @staticmethod
    def _walk(tree: Tree) -> Iterator[Blob]:
        for item in tree:
            if isinstance(item, Tree):
                yield from LocalGitProvider._walk(item)
            elif isinstance(item, Blob):
                yield item
