"""``Planner``: diff entre el objetivo renderizado y el estado actual (ENG-070/071/075).

División de responsabilidades del pipeline de despliegue (§17):

- ``DeploymentService`` (``service.py``) orquesta: resuelve el ref, hace
  checkout, valida, renderiza en **dos pasadas** (ENG-072: primero para
  identificar assets, sube los assets con ``upload_asset`` y vuelve a
  renderizar con las URLs ``pluginfile`` reales) y delega aquí el diff.
- ``Planner`` es puro respecto a Git y al renderizado: recibe el
  ``RenderedBook`` final (HTML definitivo por capítulo) y compara con el
  estado actual de Moodle vía ``MoodleProvider.get_deploy`` +
  ``get_book``. Emite el ``DeploymentPlan`` con las acciones CREATE/UPDATE/
  DELETE/UPLOAD, las eliminaciones marcadas ``requires_confirmation`` (§17.2)
  y el bloqueo de versiones RECALLED (ENG-075, §18).
- ``Executor`` (``executor.py``) aplica el plan y registra el despliegue.

El diff de capítulos compara el hash del HTML objetivo con el **HTML actual en
Moodle** (no solo con el ``content_hash`` registrado): así, si un profesor
editó el Book a mano (drift, §19.1), el siguiente despliegue de la misma
versión incluye el UPDATE que sobrescribe esos cambios.
"""

from __future__ import annotations

from collections.abc import Iterable

from courseascode.content.markdown import create_markdown
from courseascode.content.renderer import RenderedBook
from courseascode.content.sanitize import sanitize_html
from courseascode.deployment.hashes import hash_html
from courseascode.deployment.releases import NullReleasePort, ReleasePort
from courseascode.domain.deployment import (
    ActionKind,
    DeploymentAction,
    DeploymentPlan,
)
from courseascode.domain.identity import ContentId
from courseascode.domain.semver import SemVer
from courseascode.moodle.provider import MoodleProvider, RemoteBook


class RecalledVersionError(RuntimeError):
    """La versión objetivo está RECALLED y el despliegue no va con ``force`` (ENG-075)."""


class Planner:
    """Genera ``DeploymentPlan`` comparando el objetivo con Moodle (ENG-070)."""

    def __init__(self, moodle: MoodleProvider, releases: ReleasePort | None = None) -> None:
        self._moodle = moodle
        self._releases = releases or NullReleasePort()

    def plan(  # noqa: PLR0913 - API del planner: diff completo en una llamada
        self,
        courseid: int,
        source: str,
        book_id: str,
        target: RenderedBook,
        target_version: SemVer,
        *,
        git_ref: str = "",
        git_commit: str = "",
        force: bool = False,
        uploaded_assets: Iterable[str] = (),
    ) -> DeploymentPlan:
        """Diff entre el estado actual en Moodle y el ``target`` renderizado.

        Args:
            courseid: ID del curso Moodle.
            source: fuente del contenido (namespace, p. ej. ``dwes``).
            book_id: id estable del Book (``book.yml``).
            target: ``RenderedBook`` de la **segunda pasada** (URLs reales).
            target_version: versión SemVer que se va a desplegar.
            git_ref / git_commit: procedencia Git (quedan en el registro).
            force: permite desplegar una versión RECALLED (con aviso, ENG-075).
            uploaded_assets: assets que la primera pasada del pipeline acaba de
                subir (cambios de contenido); quedan como acciones UPLOAD
                documentales en el plan (la subida ya ocurrió, ENG-072).
        """
        if self._releases.is_recalled(source, book_id, target_version) and not force:
            msg = (
                f"la versión {target_version} de @{source}/{book_id} está RECALLED:"
                " despliegue bloqueado (usa --force para forzar, §18)"
            )
            raise RecalledVersionError(msg)
        warnings: list[str] = []
        if force and self._releases.is_recalled(source, book_id, target_version):
            warnings.append(f"despliegue FORZADO de la versión RECALLED {target_version} (§18)")

        record = self._moodle.get_deploy(courseid, source, book_id)
        current_version = SemVer.parse(record.content_version) if record else None
        remote = self._load_remote(record.bookid if record else None)

        actions: list[DeploymentAction] = []
        book_action = self._book_action(target, remote)
        if book_action is not None:
            actions.append(book_action)

        target_ids: set[str] = set()
        for position, chapter in enumerate(target.chapters, start=1):
            target_ids.add(chapter.stable_id)
            target_hash = hash_html(chapter.html)
            current = remote.chapters.get(chapter.stable_id) if remote else None
            if current is None:
                kind = ActionKind.CREATE
            elif hash_html(current.html) != target_hash:
                # UPDATE si difiere del HTML actual en Moodle. Incluye el drift
                # (§19.1): el HTML actual fue editado a mano y difiere del
                # hash registrado, así que también difiere del objetivo.
                kind = ActionKind.UPDATE
            else:
                continue
            actions.append(
                DeploymentAction(
                    kind=kind,
                    target="chapter",
                    stable_id=chapter.stable_id,
                    title=chapter.title,
                    html=chapter.html,
                    position=position,
                )
            )

        if remote is not None:
            for stable_id, current in sorted(remote.chapters.items()):
                if stable_id not in target_ids:
                    actions.append(
                        DeploymentAction(
                            kind=ActionKind.DELETE,
                            target="chapter",
                            stable_id=stable_id,
                            title=current.title,
                            requires_confirmation=True,  # §17.2: nunca borrar en silencio
                        )
                    )

        for asset_path in sorted(uploaded_assets):
            actions.append(
                DeploymentAction(kind=ActionKind.UPLOAD, target="asset", asset_path=asset_path)
            )

        return DeploymentPlan(
            course_id=courseid,
            content=ContentId(source, book_id),
            current_version=current_version,
            target_version=target_version,
            actions=tuple(actions),
            git_ref=git_ref,
            git_commit=git_commit,
            warnings=tuple(warnings),
        )

    # -- helpers internos ---------------------------------------------------------

    def _load_remote(self, bookid: int | None) -> RemoteBook | None:
        """Estado actual del Book en Moodle; ``None`` si no existe (aún o ya no)."""
        if bookid is None:
            return None
        return self._moodle.get_book(bookid)

    @staticmethod
    def _book_action(target: RenderedBook, remote: RemoteBook | None) -> DeploymentAction | None:
        """CREATE/UPDATE del Book si no existe o cambian nombre/intro/numbering."""
        intro = _render_intro(target.book.description)
        numbering = str(target.book.numbering)
        if remote is None:
            return DeploymentAction(
                kind=ActionKind.CREATE,
                target="book",
                title=target.book.title,
                html=intro,
                numbering=numbering,
            )
        if (
            remote.name != target.book.title
            or remote.intro != intro
            or str(remote.numbering) != numbering
        ):
            return DeploymentAction(
                kind=ActionKind.UPDATE,
                target="book",
                title=target.book.title,
                html=intro,
                numbering=numbering,
            )
        return None


def _render_intro(description: str) -> str:
    """Intro del Book Moodle: la descripción del manifest renderizada a HTML."""
    return sanitize_html(create_markdown().render(description))
