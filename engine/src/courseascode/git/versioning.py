"""Resolución de versiones desde tags Git y ramas personales (§8, ENG-023-025)."""

from __future__ import annotations

from courseascode.domain.semver import SemVer, SemVerError
from courseascode.git.provider import GitProvider

_TAG_GLOB = "book/{book_id}/v*"


class VersionResolver:
    """Resuelve versiones de Books a partir de tags y ramas.

    - Línea oficial: tags ``book/<id>/vX.Y.Z`` (§8.1).
    - Ramas personales: versión derivada ``tag base + commits ahead``
      (§8.2), p. ej. ``1.2.0+juan.3``.
    """

    def __init__(self, provider: GitProvider) -> None:
        self._provider = provider

    def versions_for(self, book_id: str) -> list[tuple[str, SemVer]]:
        """Todos los tags de un Book como ``(tag, SemVer)``, ordenados asc."""
        versions: list[tuple[str, SemVer]] = []
        for tag in self._provider.list_tags(_TAG_GLOB.format(book_id=book_id)):
            try:
                versions.append((tag, SemVer.from_tag(tag)))
            except SemVerError:
                continue  # tag con formato inesperado: se ignora
        versions.sort(key=lambda pair: pair[1])
        return versions

    def latest(self, book_id: str) -> tuple[str, SemVer] | None:
        """Última versión oficial taggeada del Book, o ``None`` si no tiene tags."""
        versions = self.versions_for(book_id)
        return versions[-1] if versions else None

    def derived_version(
        self,
        book_id: str,
        branch: str = "HEAD",
        base_branch: str = "main",
        source: str | None = None,
    ) -> SemVer:
        """Versión calculada de una rama: base oficial + build ``<source>.<ahead>``.

        La base es el tag oficial más reciente que ya está contenido en el
        merge-base con la rama oficial. Sin tags base: ``0.0.0+<source>.<ahead>``.
        """
        source_name = source or branch
        merge_base = self._provider.merge_base(base_branch, branch)
        base = self._base_version(book_id, merge_base)
        ahead = self._provider.commits_ahead(merge_base, branch)
        return SemVer(base.major, base.minor, base.patch, build=f"{source_name}.{ahead}")

    def _base_version(self, book_id: str, merge_base: str) -> SemVer:
        candidates = [
            version
            for tag, version in self.versions_for(book_id)
            if self._provider.is_ancestor(self._provider.get_commit(tag), merge_base)
        ]
        return max(candidates) if candidates else SemVer(0, 0, 0)


def detect_source(provider: GitProvider) -> str:
    """Fuente actual del repo compartido: nombre de la rama (ENG-025).

    En ``main`` la línea es oficial; el namespace de visualización (``@dwes``)
    es configuración de presentación, no de Git.
    """
    return provider.current_branch()
