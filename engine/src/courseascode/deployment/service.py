"""Servicio de despliegue: orquesta el pipeline completo de §17.

Pipeline (los pasos 8-11 viven repartidos entre ``Planner`` y ``Executor``,
cuya división de responsabilidades está documentada en ``planner.py``):

1. Resolver el git_ref (tag, rama o commit; sin ``--version``/``--ref``, la
   última versión taggeada, §18).
2. Checkout aislado del contenido (``GitProvider.checkout_ref``).
3-4. Validar manifests y capítulos (``Validator``, §20): un repo inválido no
   se puede publicar.
5-7. **Assets en dos pasadas** (ENG-072): renderizar con placeholders para
   identificar los assets, subirlos con ``upload_asset`` → URLs
   ``pluginfile.php`` reales, y volver a renderizar con ``MoodleAssetAdapter``
   alimentado con esas URLs (y ``MoodleLinkAdapter`` con las URLs de los
   capítulos que ya existen en Moodle). El diff de archivos de la sección
   ``Changes`` del plan sale de ``GitProvider.diff`` entre lo desplegado y el
   objetivo.
8. Generar el ``DeploymentPlan`` (``Planner``).
9. [Confirmación del usuario, salvo ``--yes``: la gestionan CLI (ENG-076) y
   el caller de la API vía ``confirmed_deletions``].
10-12. Ejecutar el plan (``Executor``) y devolver el ``DeploymentResult``.

Deploy de una versión anterior = rollback (§18): es el mismo pipeline, sin
código especial (ENG-077).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from courseascode.content.links import MoodleAssetAdapter, MoodleLinkAdapter
from courseascode.content.markdown import create_markdown
from courseascode.content.renderer import RenderedBook, render_book
from courseascode.content.sanitize import sanitize_html
from courseascode.deployment.executor import Executor
from courseascode.deployment.hashes import hash_bytes
from courseascode.deployment.planner import Planner
from courseascode.deployment.releases import ReleasePort
from courseascode.deployment.state import StateInfo, compute_state
from courseascode.domain.deployment import DeploymentPlan, DeploymentResult
from courseascode.domain.identity import ContentId, RefKind
from courseascode.domain.semver import SemVer, SemVerError
from courseascode.git.provider import GitProvider, GitProviderError
from courseascode.git.versioning import VersionResolver
from courseascode.manifests.models import BookManifest
from courseascode.manifests.parser import ManifestParser
from courseascode.manifests.validator import Validator
from courseascode.moodle.provider import MoodleProvider, RemoteBook


class DeploymentServiceError(RuntimeError):
    """El pipeline no puede continuar: validación fallida, ref inexistente…"""


@dataclass(frozen=True)
class BookStatus:
    """Fila de ``courseascode status``: estado de un Book desplegado en un curso."""

    content: ContentId
    state: StateInfo


class DeploymentService:
    """Orchestra el pipeline de publicación (§17) entre Git, el renderer y Moodle.

    ``git`` puede ser ``None`` para consultas de estado sin repo (no hay
    "última versión" que comparar); ``plan``/``deploy`` requieren provider.
    """

    def __init__(
        self,
        git: GitProvider | None,
        moodle: MoodleProvider,
        releases: ReleasePort | None = None,
        *,
        source: str = "dwes",
    ) -> None:
        self._git = git
        self._moodle = moodle
        self._releases = releases
        self._source = source

    # -- plan y deploy (§17) ------------------------------------------------------

    def plan(
        self,
        courseid: int,
        book_id: str,
        *,
        version: str | None = None,
        ref: str | None = None,
        force: bool = False,
    ) -> DeploymentPlan:
        """Genera el plan de despliegue sin tocar Moodle más que para leer estado.

        Sí crea/actualiza el Book y sube los assets de la primera pasada: son
        operaciones idempotentes necesarias para obtener las URLs del render
        final (ENG-072). Lo que nunca hace es crear/actualizar/borrar capítulos
        ni registrar el despliegue: eso es ``deploy``.
        """
        ref_name, target_version = self._resolve_ref(book_id, version, ref)
        git = self._git
        assert git is not None  # _resolve_ref exige un provider Git
        commit = git.get_commit(ref_name)
        with git.checkout_ref(ref_name) as root:
            report = Validator().validate(root)
            if not report.ok:
                raise DeploymentServiceError(
                    f"validación fallida en {ref_name}; no se puede publicar:\n{report.render()}"
                )
            book_path, book_dir, book = self._load_book(root, book_id)
            self._moodle.get_course(courseid)  # falla con MoodleError si no existe

            record = self._moodle.get_deploy(courseid, self._source, book_id)
            bookid = record.bookid if record else None
            remote = self._moodle.get_book(bookid) if bookid is not None else None

            intro = _render_intro(book)
            if bookid is None:
                # Primer despliegue: hay que crear el Book para poder subir
                # assets (idempotente: en despliegues siguientes bookid viene
                # del registro y el planner detecta los cambios de metadatos).
                bookid = self._moodle.upsert_book(courseid, book.title, intro, book.numbering)

            first = render_book(book_dir, book, MoodleLinkAdapter({}), MoodleAssetAdapter({}))
            urls, uploaded = self._upload_assets(bookid, first, remote)
            links = {sid: chapter.url for sid, chapter in remote.chapters.items()} if remote else {}
            final = render_book(book_dir, book, MoodleLinkAdapter(links), MoodleAssetAdapter(urls))

            plan = Planner(self._moodle, self._releases).plan(
                courseid,
                self._source,
                book_id,
                final,
                target_version,
                git_ref=ref_name,
                git_commit=commit,
                force=force,
                uploaded_assets=uploaded,
            )
            changes = self._changes(
                record.git_ref if record else None, ref_name, book_path, book, first
            )
            return plan.model_copy(update={"changes": tuple(changes)})

    def deploy(  # noqa: PLR0913 - pipeline completo: una opción por flag (§17.1)
        self,
        courseid: int,
        book_id: str,
        *,
        version: str | None = None,
        ref: str | None = None,
        assume_yes: bool = False,
        confirmed_deletions: bool = False,
        force: bool = False,
        deployed_by: str = "api",
    ) -> DeploymentResult:
        """Ejecuta el pipeline completo. Las eliminaciones requieren confirmación
        (``confirmed_deletions`` o ``assume_yes``, §17.2)."""
        plan = self.plan(courseid, book_id, version=version, ref=ref, force=force)
        if not plan.actions:
            return DeploymentResult(
                success=True,
                message=(
                    f"@{plan.content} ya está desplegado en v{plan.target_version}: nada que hacer."
                ),
                version=str(plan.target_version),
                commit=plan.git_commit,
            )
        return Executor(self._moodle).execute(
            plan,
            confirmed_deletions=confirmed_deletions or assume_yes,
            deployed_by=deployed_by,
        )

    # -- estado (§19) -------------------------------------------------------------

    def state(
        self,
        courseid: int,
        book_id: str,
        *,
        source: str | None = None,
    ) -> StateInfo:
        """Estado del despliegue, con la última versión taggeada como objetivo."""
        target = self._latest_version(book_id)
        return compute_state(
            self._moodle, self._releases, courseid, source or self._source, book_id, target
        )

    def course_status(self, courseid: int) -> list[BookStatus]:
        """Estado de todos los Books desplegados en el curso (para ``status``).

        Limitación documentada (ENG-078): el provider no lista cursos globales,
        así que el listado es por curso; los Books son las claves
        ``(source, content_id)`` distintas del historial de despliegues.
        """
        latest: dict[tuple[str, str], StateInfo] = {}
        for record in self._moodle.list_deploys(courseid):
            key = (record.source, record.content_id)
            if key in latest:
                continue  # list_deploys viene más reciente primero
            target = self._latest_version(record.content_id)
            latest[key] = compute_state(
                self._moodle, self._releases, courseid, record.source, record.content_id, target
            )
        return [
            BookStatus(content=ContentId(source, book_id), state=state)
            for (source, book_id), state in sorted(latest.items())
        ]

    def where(self, source: str, book_id: str, version: str) -> list[int]:
        """Cursos con ``version`` como despliegue actual (consulta inversa, ENG-079)."""
        return self._moodle.where_deployed(source, book_id, version)

    # -- helpers internos ---------------------------------------------------------

    def _resolve_ref(
        self, book_id: str, version: str | None, ref: str | None
    ) -> tuple[str, SemVer]:
        """Resuelve (ref, SemVer) objetivo a partir de ``--version`` o ``--ref``."""
        if self._git is None:
            raise DeploymentServiceError("se requiere un repositorio Git para desplegar")
        if version is not None and ref is not None:
            raise DeploymentServiceError("usa --version o --ref, no ambos")
        if version is not None:
            try:
                semver = SemVer.parse(version)
            except SemVerError as exc:
                raise DeploymentServiceError(str(exc)) from exc
            return f"book/{book_id}/v{semver}", semver
        if ref is not None:
            try:
                git_ref = self._git.get_ref(ref)
            except GitProviderError as exc:
                raise DeploymentServiceError(str(exc)) from exc
            if git_ref.kind is RefKind.TAG:
                return ref, SemVer.from_tag(ref)
            if git_ref.kind is RefKind.BRANCH:
                resolver = VersionResolver(self._git)
                return ref, resolver.derived_version(book_id, branch=ref)
            return ref, SemVer(0, 0, 0, build=ref[:7])
        latest = VersionResolver(self._git).latest(book_id)
        if latest is None:
            raise DeploymentServiceError(
                f"el book {book_id!r} no tiene versiones taggeadas;"
                " usa --ref para desplegar un ref concreto"
            )
        return latest

    @staticmethod
    def _load_book(root: Path, book_id: str) -> tuple[str, Path, BookManifest]:
        """``(path relativo en course.yml, directorio, manifest)`` del Book."""
        course = ManifestParser(root).parse_course()
        book_ref = next((b for b in course.books if b.id == book_id), None)
        if book_ref is None:
            raise DeploymentServiceError(f"el book {book_id!r} no está en course.yml")
        return (
            book_ref.path,
            root / book_ref.path,
            ManifestParser(root).parse_book(root / book_ref.path),
        )

    def _upload_assets(
        self, bookid: int, rendered: RenderedBook, remote: RemoteBook | None
    ) -> tuple[dict[str, str], list[str]]:
        """Sube todos los assets referenciados y devuelve ``(urls, subidos_nuevos)``.

        La subida siempre ocurre (idempotente: sobrescribe, §15) para obtener
        las URLs del render final; ``subidos_nuevos`` lista solo los que
        cambiaban respecto al estado actual (los que el plan documenta como
        acciones UPLOAD).
        """
        urls: dict[str, str] = {}
        uploaded: list[str] = []
        for asset in rendered.assets:
            data = asset.local_path.read_bytes()
            filename = PurePosixPath(asset.path).name
            if remote is None or remote.assets.get(filename) != hash_bytes(data):
                uploaded.append(asset.path)
            urls[asset.path] = self._moodle.upload_asset(bookid, filename, data)
        return urls, uploaded

    def _changes(
        self,
        current_ref: str | None,
        target_ref: str,
        book_path: str,
        book: BookManifest,
        rendered: RenderedBook,
    ) -> list[str]:
        """Sección ``Changes`` del plan (§17.1): diff de archivos del Book."""
        markers = {"added": "+", "modified": "~", "deleted": "-", "renamed": "~"}
        if current_ref is None:
            return [f"+ {c.file}" for c in book.chapters] + [f"+ {a.path}" for a in rendered.assets]
        try:
            diff = self._git.diff(current_ref, target_ref)  # type: ignore[union-attr]
        except GitProviderError:
            return []
        prefix = book_path.rstrip("/") + "/"
        return [
            f"{markers[change.status]} {change.path[len(prefix) :]}"
            for change in diff.changes
            if change.path.startswith(prefix)
        ]

    def _latest_version(self, book_id: str) -> SemVer | None:
        if self._git is None:
            return None
        try:
            latest = VersionResolver(self._git).latest(book_id)
        except GitProviderError:
            return None
        return latest[1] if latest else None


def _render_intro(book: BookManifest) -> str:
    """Intro del Book Moodle: descripción del manifest renderizada a HTML."""
    return sanitize_html(create_markdown().render(book.description))
