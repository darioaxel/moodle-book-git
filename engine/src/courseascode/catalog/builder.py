"""Constructor del catálogo derivado del repo (ENG-050/051, §12.2)."""

from __future__ import annotations

from pathlib import Path

from courseascode.catalog.models import Catalog, CatalogEntry, CatalogVersion
from courseascode.domain.semver import SemVer
from courseascode.git.provider import GitProvider, GitProviderError
from courseascode.git.versioning import VersionResolver
from courseascode.manifests.errors import ManifestError
from courseascode.manifests.models import CourseManifest
from courseascode.manifests.parser import ManifestParser

# Rama de la línea oficial, usada solo para leer ``course.yml`` cuando no se
# da ``course_root`` (ver decisión en la docstring de ``CatalogBuilder``).
_OFFICIAL_BRANCH = "main"


class CatalogError(RuntimeError):
    """No se puede derivar el catálogo (course.yml ilegible, tag sin book.yml, ...)."""


def _course_error(exc: Exception) -> str:
    return f"no se puede leer course.yml de {_OFFICIAL_BRANCH!r}: {exc}"


class CatalogBuilder:
    """Deriva el catálogo de los ``book.yml`` en el último tag de cada Book.

    Decisiones de diseño:

    - La **lista de Books** se lee del ``course.yml`` del *working tree*
      (``course_root``): es el manifiesto vivo del curso y no necesita Git.
      Si no se pasa ``course_root``, se lee de un checkout aislado de la rama
      oficial (``main``). El nombre de la fuente no vive en el repo: se pasa
      a ``build()`` (en la Beta siempre es la fuente oficial del registry).
    - Los **metadatos** (summary, tags, audience, cover) y el nº de capítulos
      se leen del ``book.yml`` del **último tag** del Book, nunca del working
      tree: el catálogo solo refleja versiones taggeadas (ENG-051).
    - Las versiones se ordenan ascendentemente por SemVer; ``latest`` es la
      última. Un Book sin tags ``book/<id>/v*`` se omite del catálogo.
    """

    def __init__(self, provider: GitProvider, course_root: Path | None = None) -> None:
        self._provider = provider
        self._resolver = VersionResolver(provider)
        self._course_root = course_root

    def build(self, source: str) -> Catalog:
        """Construye el catálogo de la fuente ``source``.

        Args:
            source: nombre del namespace (p. ej. ``dwes``); es de presentación,
                el repo no lo almacena.

        Raises:
            CatalogError: si ``course.yml`` no se puede leer o un tag no tiene
                ``book.yml`` parseable.
        """
        course = self._course()
        books: list[CatalogEntry] = []
        for book_ref in course.books:
            versions = self._resolver.versions_for(book_ref.id)
            if not versions:
                continue  # ENG-051: sin tags oficiales no hay entrada de catálogo
            books.append(self._entry(book_ref.path, versions))
        return Catalog(source=source, books=tuple(books))

    # -- internals -------------------------------------------------------------

    def _course(self) -> CourseManifest:
        if self._course_root is not None:
            try:
                return ManifestParser(self._course_root).parse_course()
            except ManifestError as exc:
                raise CatalogError(f"no se puede leer course.yml: {exc}") from exc
        try:
            with self._provider.checkout_ref(_OFFICIAL_BRANCH) as root:
                return ManifestParser(root).parse_course()
        except GitProviderError as exc:
            raise CatalogError(_course_error(exc)) from exc
        except ManifestError as exc:
            raise CatalogError(_course_error(exc)) from exc

    def _entry(self, book_path: str, versions: list[tuple[str, SemVer]]) -> CatalogEntry:
        latest_tag, latest = versions[-1]
        with self._provider.checkout_ref(latest_tag) as root:
            try:
                book = ManifestParser(root).parse_book(root / book_path)
            except ManifestError as exc:
                raise CatalogError(f"book.yml inválido en {latest_tag!r}: {exc}") from exc
        return CatalogEntry(
            id=book.id,
            title=book.title,
            type=book.type,
            summary=book.summary,
            description=book.description,
            tags=book.tags,
            audience=book.audience,
            cover=book.cover,
            chapter_count=len(book.chapters),
            versions=tuple(CatalogVersion(tag=tag, version=version) for tag, version in versions),
            latest=str(latest),
        )
