"""``FakeMoodleProvider``: implementación en memoria de ``MoodleProvider`` (ENG-063).

Simula fielmente el contrato del plugin (§5.3b) para que los tests del
deployment engine (Fase 7) sean significativos sin necesidad de Moodle:

- Books por curso: ``upsert_book`` idempotente (dos llamadas → un Book, mismo
  ``bookid``).
- Capítulos indexados por su ``id`` estable: repetir ``upsert_chapter`` con el
  mismo stable id actualiza en el mismo capítulo, nunca duplica. El orden se
  deriva de ``position``.
- Assets con URL ``pluginfile://<bookid>/<filename>`` simulada; re-subir el
  mismo filename sobrescribe.
- Tabla de despliegues: ``register_deploy`` añade historial; ``get_deploy``
  devuelve el más reciente por ``(courseid, source, content_id)``;
  ``list_deploys`` ordena más reciente primero.
- Validaciones del contrato: operaciones sobre ``bookid`` inexistente,
  capítulo inexistente o curso no dado de alta → ``MoodleError`` con el
  formato ``errorcode (exception): mensaje`` que usaría Moodle.

Determinista: sin red, sin sleeps, sin reloj real (``deployed_at`` lo fija el
llamante en el ``DeployRecord``).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from courseascode.domain.content import Numbering
from courseascode.moodle.provider import (
    DeployRecord,
    MoodleCourse,
    MoodleError,
    MoodleProvider,
)


@dataclass
class _FakeBook:
    bookid: int
    courseid: int
    name: str
    intro: str
    numbering: Numbering
    chapters: dict[str, tuple[str, str, int]] = field(default_factory=dict)
    # stable_id -> (title, content_html, position)
    assets: dict[str, bytes] = field(default_factory=dict)


class FakeMoodleProvider(MoodleProvider):
    """Moodle en memoria para tests (ENG-063)."""

    def __init__(self, course_ids: tuple[int, ...] = ()) -> None:
        self._courses: dict[int, MoodleCourse] = {
            course_id: {
                "id": course_id,
                "fullname": f"Curso {course_id}",
                "shortname": f"C{course_id}",
            }
            for course_id in course_ids
        }
        self._books: dict[int, _FakeBook] = {}
        self._deploys: list[DeployRecord] = []
        self._next_bookid = 1
        self._next_deploy_id = 1

    def add_course(self, course_id: int, fullname: str = "", shortname: str = "") -> None:
        """Da de alta un curso en el fake (equivalente a crearlo en Moodle)."""
        self._courses[course_id] = {
            "id": course_id,
            "fullname": fullname or f"Curso {course_id}",
            "shortname": shortname or f"C{course_id}",
        }

    def get_course(self, course_id: int) -> MoodleCourse:
        try:
            return self._courses[course_id]
        except KeyError:
            msg = (
                "core_course_get_courses: invalid_course (dml_missing_record_exception):"
                f" no existe el curso {course_id}"
            )
            raise MoodleError(msg) from None

    def get_deploy(self, courseid: int, source: str, content_id: str) -> DeployRecord | None:
        matches = [
            record
            for record in self._deploys
            if record.courseid == courseid
            and record.source == source
            and record.content_id == content_id
        ]
        if not matches:
            return None
        return max(matches, key=lambda r: (r.deployed_at, r.id or 0))

    def upsert_book(self, courseid: int, name: str, intro: str, numbering: Numbering) -> int:
        self._require_course(courseid)
        for book in self._books.values():
            if book.courseid == courseid and book.name == name:
                book.intro = intro
                book.numbering = numbering
                return book.bookid
        bookid = self._next_bookid
        self._next_bookid += 1
        self._books[bookid] = _FakeBook(bookid, courseid, name, intro, numbering)
        return bookid

    def upsert_chapter(
        self,
        bookid: int,
        chapter_stable_id: str,
        title: str,
        content_html: str,
        position: int,
    ) -> None:
        book = self._require_book(bookid, "local_courseascode_upsert_chapter")
        book.chapters[chapter_stable_id] = (title, content_html, position)

    def delete_chapter(self, bookid: int, chapter_stable_id: str) -> None:
        book = self._require_book(bookid, "local_courseascode_delete_chapter")
        if chapter_stable_id not in book.chapters:
            msg = (
                "local_courseascode_delete_chapter: chapter_not_found"
                f" (dml_missing_record_exception): el Book {bookid} no tiene el capítulo"
                f" {chapter_stable_id!r}"
            )
            raise MoodleError(msg)
        del book.chapters[chapter_stable_id]

    def upload_asset(self, bookid: int, filename: str, data: bytes) -> str:
        book = self._require_book(bookid, "local_courseascode_upload_asset")
        book.assets[filename] = data
        return f"pluginfile://{bookid}/{filename}"

    def register_deploy(self, record: DeployRecord) -> int:
        self._require_book(record.bookid, "local_courseascode_register_deploy")
        deploy_id = self._next_deploy_id
        self._next_deploy_id += 1
        self._deploys.append(record.model_copy(update={"id": deploy_id}))
        return deploy_id

    def list_deploys(self, courseid: int) -> list[DeployRecord]:
        matches = [r for r in self._deploys if r.courseid == courseid]
        return sorted(matches, key=lambda r: (r.deployed_at, r.id or 0), reverse=True)

    # -- introspección para tests -------------------------------------------------

    def get_book(self, bookid: int) -> _FakeBook:
        """Acceso al estado interno de un Book (asserts de tests)."""
        return self._require_book(bookid, "fake.get_book")

    def chapter_titles_in_order(self, bookid: int) -> list[str]:
        """Títulos de capítulo ordenados por position (como se vería en Moodle)."""
        book = self._require_book(bookid, "fake.chapter_titles_in_order")
        ordered = sorted(book.chapters.items(), key=lambda item: item[1][2])
        return [title for _, (title, _, _) in ordered]

    # -- validaciones internas ----------------------------------------------------

    def _require_course(self, courseid: int) -> MoodleCourse:
        try:
            return self._courses[courseid]
        except KeyError:
            msg = (
                "local_courseascode: invalid_course (dml_missing_record_exception):"
                f" no existe el curso {courseid}"
            )
            raise MoodleError(msg) from None

    def _require_book(self, bookid: int, wsfunction: str) -> _FakeBook:
        try:
            return self._books[bookid]
        except KeyError:
            msg = (
                f"{wsfunction}: invalid_book (dml_missing_record_exception):"
                f" no existe un Book con id {bookid}"
            )
            raise MoodleError(msg) from None
