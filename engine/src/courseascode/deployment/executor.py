"""``Executor``: aplica un ``DeploymentPlan`` vía ``MoodleProvider`` (ENG-073).

Responsabilidades (la división completa del pipeline está documentada en
``planner.py``):

- Asegura el Book (upsert idempotente) y aplica los capítulos en el orden del
  manifest (``position`` 1-based), identificados por su stable id: re-ejecutar
  el mismo plan nunca duplica (§17.3).
- Resuelve los placeholders de enlaces internos (``#chapter-<id>``): tras
  crear/actualizar los capítulos, los enlaces a capítulos que ya existen se
  reescriben con su URL real y se vuelven a subir afectados. Gracias a esto el
  rollback es byte-exacto (ENG-077) y §16 ("nunca quedan enlaces rotos")
  se cumple en el mismo despliegue, no en el siguiente.
- Las eliminaciones solo se ejecutan con ``confirmed_deletions=True`` (§17.2);
  sin confirmación se omiten y quedan avisadas en el resultado.
- Las acciones UPLOAD son **documentales** en el pipeline real: el servicio ya
  subió los assets entre la primera y la segunda pasada del render (ENG-072).
  Si una acción trae ``asset_data`` (plan construido a mano), sí se sube.
- Registra el despliegue (§17 paso 11) con el ``content_hash`` calculado sobre
  el estado **final** del Book en Moodle (un ``get_book`` tras aplicar todo),
  que es la fuente de verdad que la detección de drift (§19.1) vuelve a leer.

Errores recuperables (ENG-102): si Moodle falla a mitad de la ejecución, se
registra un despliegue con ``status="error"`` (el estado del Book pasa a
ERROR, §19) y el error propaga como ``DeploymentExecutionError``, un
``MoodleError`` con mensaje accionable: qué acción falló, sobre qué capítulo y
la sugerencia de relanzar el mismo deploy — el pipeline es idempotente (§17.3)
y continúa donde falló, sin intervención del operador.
"""

from __future__ import annotations

import time
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from html import escape
from pathlib import PurePosixPath

from courseascode.deployment.hashes import hash_html, serialize_hashes
from courseascode.domain.content import Numbering
from courseascode.domain.deployment import (
    ActionKind,
    DeploymentAction,
    DeploymentPlan,
    DeploymentResult,
)
from courseascode.moodle.provider import DeployRecord, MoodleError, MoodleProvider

_PLACEHOLDER_PREFIX = "#chapter-"
_FAILED_STATUS = "error"


class DeploymentExecutionError(MoodleError):
    """Fallo a mitad de la ejecución de un plan (ENG-102).

    Recuperable relanzando el mismo deploy: las acciones ya aplicadas son
    idempotentes (§17.3) y el planner no genera acciones para el contenido
    que ya coincide con Moodle.
    """


@dataclass
class _ActionFailure(Exception):
    """Error de Moodle con la acción que lo provocó (para el mensaje accionable).

    No es un ``MoodleError``: es control-flow interno entre los helpers de
    aplicación y ``execute``, que la envuelve en ``DeploymentExecutionError``.
    """

    action: DeploymentAction | None  # ``None`` = fuera de las acciones (p. ej. el registro)
    error: MoodleError


class Executor:
    """Aplica planes de despliegue sobre Moodle (ENG-073)."""

    def __init__(self, moodle: MoodleProvider) -> None:
        self._moodle = moodle

    def execute(
        self,
        plan: DeploymentPlan,
        *,
        confirmed_deletions: bool = False,
        deployed_by: str = "engine",
    ) -> DeploymentResult:
        """Ejecuta el plan; ``confirmed_deletions`` autoriza las eliminaciones (§17.2)."""
        started = time.monotonic()
        previous = self._moodle.get_deploy(plan.course_id, plan.content.source, plan.content.id)
        bookid = previous.bookid if previous else None
        warnings = list(plan.warnings)
        applied: list[DeploymentAction] = []

        try:
            bookid = self._apply_book(plan, bookid, applied)
            chapter_actions = self._apply_chapters(plan, bookid, applied)
            self._resolve_link_placeholders(bookid, chapter_actions)
            self._apply_deletions(plan, bookid, confirmed_deletions, applied, warnings)
            self._apply_uploads(plan, bookid, applied)
            content_hash = self._final_content_hash(bookid)
        except _ActionFailure as failure:
            self._register_failure(plan, previous, bookid, deployed_by)
            raise self._actionable_error(failure, plan) from failure.error
        except MoodleError as error:
            read_failure = _ActionFailure(action=None, error=error)
            self._register_failure(plan, previous, bookid, deployed_by)
            raise self._actionable_error(read_failure, plan) from error

        record = DeployRecord(
            courseid=plan.course_id,
            bookid=bookid,
            source=plan.content.source,
            content_id=plan.content.id,
            content_version=str(plan.target_version),
            git_ref=plan.git_ref or (previous.git_ref if previous else "unknown"),
            git_commit=plan.git_commit or (previous.git_commit if previous else "unknown"),
            content_hash=content_hash,
            deployed_at=datetime.now(UTC),
            deployed_by=deployed_by,
        )
        self._moodle.register_deploy(record)

        duration = time.monotonic() - started
        message = (
            f"Deployed @{plan.content.source}/{plan.content.id}"
            f" v{plan.target_version} (commit {record.git_commit[:7]})"
        )
        return DeploymentResult(
            success=True,
            actions_applied=tuple(applied),
            duration_seconds=duration,
            message=message,
            version=str(plan.target_version),
            commit=record.git_commit,
            warnings=tuple(warnings),
        )

    # -- aplicación de acciones ---------------------------------------------------

    def _apply_book(
        self, plan: DeploymentPlan, bookid: int | None, applied: list[DeploymentAction]
    ) -> int:
        """Asegura el Book Moodle; devuelve su ``bookid`` (idempotente)."""
        book_action = next((a for a in plan.actions if a.target == "book"), None)
        if book_action is None and bookid is not None:
            return bookid
        title = book_action.title if book_action else plan.content.id
        intro = book_action.html if book_action else ""
        numbering = Numbering(book_action.numbering) if book_action else Numbering.NUMBERS
        try:
            bookid = self._moodle.upsert_book(plan.course_id, title, intro, numbering)
        except MoodleError as error:
            raise _ActionFailure(action=book_action, error=error) from error
        if book_action is not None:
            applied.append(book_action)
        return bookid

    def _apply_chapters(
        self, plan: DeploymentPlan, bookid: int, applied: list[DeploymentAction]
    ) -> list[DeploymentAction]:
        """Crea/actualiza los capítulos en el orden del manifest; devuelve los aplicados."""
        chapter_actions = [
            action
            for action in plan.actions
            if action.target == "chapter" and action.kind in (ActionKind.CREATE, ActionKind.UPDATE)
        ]
        for action in chapter_actions:
            assert action.stable_id is not None  # las acciones de capítulo llevan stable id
            try:
                self._moodle.upsert_chapter(
                    bookid, action.stable_id, action.title, action.html, action.position
                )
            except MoodleError as error:
                raise _ActionFailure(action=action, error=error) from error
            applied.append(action)
        return chapter_actions

    def _apply_deletions(
        self,
        plan: DeploymentPlan,
        bookid: int,
        confirmed_deletions: bool,
        applied: list[DeploymentAction],
        warnings: list[str],
    ) -> None:
        """Elimina capítulos ausentes del objetivo, solo con confirmación (§17.2)."""
        deletions = [action for action in plan.actions if action.kind is ActionKind.DELETE]
        if deletions and not confirmed_deletions:
            warnings.append(
                f"{len(deletions)} eliminación(es) omitida(s): sin confirmación del usuario (§17.2)"
            )
            return
        for action in deletions:
            assert action.stable_id is not None
            try:
                self._moodle.delete_chapter(bookid, action.stable_id)
            except MoodleError as error:
                raise _ActionFailure(action=action, error=error) from error
            applied.append(action)

    def _apply_uploads(
        self, plan: DeploymentPlan, bookid: int, applied: list[DeploymentAction]
    ) -> None:
        """Sube assets de acciones UPLOAD construidas a mano (en el pipeline real
        el servicio ya los subió en la primera pasada del render, ENG-072)."""
        for action in plan.actions:
            if action.kind is not ActionKind.UPLOAD:
                continue
            if action.asset_data:
                filename = PurePosixPath(action.asset_path).name or action.title
                try:
                    self._moodle.upload_asset(bookid, filename, action.asset_data)
                except MoodleError as error:
                    raise _ActionFailure(action=action, error=error) from error
            applied.append(action)

    # -- errores recuperables (ENG-102) --------------------------------------------

    def _register_failure(
        self,
        plan: DeploymentPlan,
        previous: DeployRecord | None,
        bookid: int | None,
        deployed_by: str,
    ) -> None:
        """Registra el intento fallido (``status="error"``): el estado pasa a ERROR.

        Sin este registro, un fallo a mitad dejaría el último despliegue *de
        éxito* como "actual" y el curso parecería sincronizado pese a no
        estarlo. Si el propio registro falla, se ignora: el error original es
        el relevante.
        """
        with suppress(MoodleError):
            self._moodle.register_deploy(
                DeployRecord(
                    courseid=plan.course_id,
                    bookid=bookid if bookid is not None else (previous.bookid if previous else 0),
                    source=plan.content.source,
                    content_id=plan.content.id,
                    content_version=str(plan.target_version),
                    git_ref=plan.git_ref or (previous.git_ref if previous else "unknown"),
                    git_commit=plan.git_commit or (previous.git_commit if previous else "unknown"),
                    content_hash=previous.content_hash if previous else "interrumpido",
                    deployed_at=datetime.now(UTC),
                    deployed_by=deployed_by,
                    status=_FAILED_STATUS,
                )
            )

    @staticmethod
    def _actionable_error(failure: _ActionFailure, plan: DeploymentPlan) -> MoodleError:
        """Envuelve el error de Moodle con contexto de la acción y la sugerencia."""
        action = failure.action
        if action is None:
            where = "al leer o registrar el estado en Moodle"
        elif action.kind is ActionKind.UPLOAD:
            where = f"al subir el asset {action.asset_path!r}"
        else:
            label = action.stable_id or action.title or action.target
            where = f"al aplicar {action.kind.value} sobre {action.target} {label!r}"
        msg = (
            f"despliegue de @{plan.content.source}/{plan.content.id} interrumpido {where}:"
            f" {failure.error}\n"
            "Sugerencia: relanza el mismo deploy: el pipeline es idempotente (§17.3) y"
            " continúa donde falló, sin duplicar lo ya desplegado."
        )
        return DeploymentExecutionError(msg)

    # -- helpers internos ---------------------------------------------------------

    def _resolve_link_placeholders(
        self, bookid: int, chapter_actions: list[DeploymentAction]
    ) -> None:
        """Reescribe ``#chapter-<id>`` con la URL real de capítulos ya existentes.

        Los placeholders proceden de la segunda pasada de render para enlaces
        cuyo destino aún no existía en Moodle (ENG-072). Tras el upsert ya
        existe, así que se corrige el HTML desplegado en el mismo deploy.
        """
        pending = [action for action in chapter_actions if _PLACEHOLDER_PREFIX in action.html]
        if not pending:
            return
        remote = self._moodle.get_book(bookid)
        assert remote is not None  # el Book acaba de crearse/actualizarse arriba
        replacements = sorted(remote.chapters.items(), key=lambda item: -len(item[0]))
        for action in pending:
            assert action.stable_id is not None
            html = action.html
            for stable_id, chapter in replacements:
                # La URL se inserta con el mismo escaping que aplica el
                # renderer a los atributos: así el redeploy de la misma
                # versión compara byte a byte igual (idempotencia, §17.3).
                url = escape(chapter.url, quote=True)
                html = html.replace(f"{_PLACEHOLDER_PREFIX}{stable_id}", url)
            if html != action.html:
                self._moodle.upsert_chapter(
                    bookid, action.stable_id, action.title, html, action.position
                )

    def _final_content_hash(self, bookid: int) -> str:
        """``content_hash`` sobre el estado final del Book (fuente de verdad, §19.1)."""
        remote = self._moodle.get_book(bookid)
        assert remote is not None  # el Book existe: lo acabamos de crear/actualizar
        return serialize_hashes(
            {stable_id: hash_html(chapter.html) for stable_id, chapter in remote.chapters.items()}
        )
