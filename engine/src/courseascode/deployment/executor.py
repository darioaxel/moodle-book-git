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
"""

from __future__ import annotations

import time
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
from courseascode.moodle.provider import DeployRecord, MoodleProvider

_PLACEHOLDER_PREFIX = "#chapter-"


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
        warnings = list(plan.warnings)
        applied: list[DeploymentAction] = []

        previous = self._moodle.get_deploy(plan.course_id, plan.content.source, plan.content.id)
        bookid = previous.bookid if previous else None

        book_action = next((a for a in plan.actions if a.target == "book"), None)
        if book_action is not None or bookid is None:
            title = book_action.title if book_action else plan.content.id
            intro = book_action.html if book_action else ""
            numbering = Numbering(book_action.numbering) if book_action else Numbering.NUMBERS
            bookid = self._moodle.upsert_book(plan.course_id, title, intro, numbering)
            if book_action is not None:
                applied.append(book_action)

        chapter_actions = [
            action
            for action in plan.actions
            if action.target == "chapter" and action.kind in (ActionKind.CREATE, ActionKind.UPDATE)
        ]
        for action in chapter_actions:
            assert action.stable_id is not None  # las acciones de capítulo llevan stable id
            self._moodle.upsert_chapter(
                bookid, action.stable_id, action.title, action.html, action.position
            )
            applied.append(action)

        self._resolve_link_placeholders(bookid, chapter_actions)

        deletions = [action for action in plan.actions if action.kind is ActionKind.DELETE]
        if deletions and not confirmed_deletions:
            warnings.append(
                f"{len(deletions)} eliminación(es) omitida(s): sin confirmación del usuario (§17.2)"
            )
        else:
            for action in deletions:
                assert action.stable_id is not None
                self._moodle.delete_chapter(bookid, action.stable_id)
                applied.append(action)

        for action in plan.actions:
            if action.kind is not ActionKind.UPLOAD:
                continue
            if action.asset_data:
                filename = PurePosixPath(action.asset_path).name or action.title
                self._moodle.upload_asset(bookid, filename, action.asset_data)
            applied.append(action)

        content_hash = self._final_content_hash(bookid)
        commit = plan.git_commit or (previous.git_commit if previous else "unknown")
        record = DeployRecord(
            courseid=plan.course_id,
            bookid=bookid,
            source=plan.content.source,
            content_id=plan.content.id,
            content_version=str(plan.target_version),
            git_ref=plan.git_ref or (previous.git_ref if previous else "unknown"),
            git_commit=commit,
            content_hash=content_hash,
            deployed_at=datetime.now(UTC),
            deployed_by=deployed_by,
        )
        self._moodle.register_deploy(record)

        duration = time.monotonic() - started
        message = (
            f"Deployed @{plan.content.source}/{plan.content.id}"
            f" v{plan.target_version} (commit {commit[:7]})"
        )
        return DeploymentResult(
            success=True,
            actions_applied=tuple(applied),
            duration_seconds=duration,
            message=message,
            version=str(plan.target_version),
            commit=commit,
            warnings=tuple(warnings),
        )

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
