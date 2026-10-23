"""``FakeMoodleProvider``: implementación en memoria de ``MoodleProvider`` (ENG-063).

Simula fielmente el contrato del plugin (§5.3b) para que los tests del
deployment engine (Fase 7) sean significativos sin necesidad de Moodle:

- Books por curso: ``upsert_book`` idempotente (dos llamadas → un Book, mismo
  ``bookid``).
- Capítulos indexados por su ``id`` estable: repetir ``upsert_chapter`` con el
  mismo stable id actualiza en el mismo capítulo, nunca duplica. El orden se
  deriva de ``position``. El ``chapterid`` (y por tanto la URL de vista) es
  estable por ``(bookid, stable_id)``: eliminar y recrear un capítulo conserva
  su URL (rollback exacto, ENG-077).
- Assets con URL ``https://moodle.local/pluginfile.php/<bookid>/<filename>``
  (el dominio es simulado; el formato http(s) coincide con Moodle real, que
  así pasa la sanitización del renderer); re-subir el mismo filename
  sobrescribe. ``get_book`` expone ``filename → sha256``.
- Tabla de despliegues: ``register_deploy`` añade historial; ``get_deploy``
  devuelve el más reciente por ``(courseid, source, content_id)``;
  ``list_deploys`` ordena más reciente primero; ``where_deployed`` devuelve
  los cursos cuyo despliegue actual es una versión dada.
- Validaciones del contrato: operaciones sobre ``bookid`` inexistente,
  capítulo inexistente o curso no dado de alta → ``MoodleError`` con el
  formato ``errorcode (exception): mensaje`` que usaría Moodle.

Determinista: sin red, sin sleeps, sin reloj real (``deployed_at`` lo fija el
llamante en el ``DeployRecord``).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

from courseascode.domain.content import Numbering
from courseascode.moodle.provider import (
    DeployRecord,
    MoodleCourse,
    MoodleError,
    MoodleProvider,
    RemoteBook,
    RemoteChapter,
)


@dataclass
class _FakeBook:
    bookid: int
    courseid: int
    name: str
    intro: str
    numbering: Numbering
    chapters: dict[str, RemoteChapter] = field(default_factory=dict)
    # stable_id -> RemoteChapter(title, html, position, url)
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
        # (bookid, stable_id) -> chapterid persistente: la URL de un capítulo
        # es estable aunque se elimine y se recree (rollback exacto, ENG-077).
        self._chapter_ids: dict[tuple[int, str], int] = {}
        self._next_chapter_id = 1
        # Inyección de fallos para ENG-102: operación -> llamadas restantes
        # que deben fallar con MoodleError antes de ejecutarse de verdad.
        self._failures: dict[str, int] = {}

    def fail_next(self, operation: str, *, times: int = 1) -> None:
        """Programa ``times`` fallos (``MoodleError``) en la operación dada.

        ``operation`` es el nombre del método: ``upsert_book``,
        ``upsert_chapter``, ``delete_chapter``, ``upload_asset`` o
        ``register_deploy``. Sirve para simular un Moodle que falla a mitad
        de un despliegue y verificar la recuperación por idempotencia.
        """
        self._failures[operation] = self._failures.get(operation, 0) + times

    def _maybe_fail(self, operation: str) -> None:
        remaining = self._failures.get(operation, 0)
        if remaining > 0:
            self._failures[operation] = remaining - 1
            msg = f"fake: fallo inyectado en {operation} (simulación de un error de Moodle)"
            raise MoodleError(msg)

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
        self._maybe_fail("upsert_book")
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
        self._maybe_fail("upsert_chapter")
        book = self._require_book(bookid, "local_courseascode_upsert_chapter")
        key = (bookid, chapter_stable_id)
        if key not in self._chapter_ids:
            self._chapter_ids[key] = self._next_chapter_id
            self._next_chapter_id += 1
        chapterid = self._chapter_ids[key]
        url = f"/mod/book/view.php?id={bookid}&chapterid={chapterid}"
        book.chapters[chapter_stable_id] = RemoteChapter(
            title=title, html=content_html, position=position, url=url
        )

    def delete_chapter(self, bookid: int, chapter_stable_id: str) -> None:
        self._maybe_fail("delete_chapter")
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
        self._maybe_fail("upload_asset")
        book = self._require_book(bookid, "local_courseascode_upload_asset")
        book.assets[filename] = data
        return f"https://moodle.local/pluginfile.php/{bookid}/mod_book/{filename}"

    def register_deploy(self, record: DeployRecord) -> int:
        self._maybe_fail("register_deploy")
        self._require_book(record.bookid, "local_courseascode_register_deploy")
        deploy_id = self._next_deploy_id
        self._next_deploy_id += 1
        self._deploys.append(record.model_copy(update={"id": deploy_id}))
        return deploy_id

    def list_deploys(self, courseid: int) -> list[DeployRecord]:
        matches = [r for r in self._deploys if r.courseid == courseid]
        return sorted(matches, key=lambda r: (r.deployed_at, r.id or 0), reverse=True)

    def get_book(self, bookid: int) -> RemoteBook | None:
        """Estado actual del Book (8ª función asumida del plugin, ENG-074)."""
        try:
            book = self._books[bookid]
        except KeyError:
            return None
        return RemoteBook(
            bookid=book.bookid,
            courseid=book.courseid,
            name=book.name,
            intro=book.intro,
            numbering=book.numbering,
            chapters=dict(book.chapters),
            assets={
                filename: hashlib.sha256(data).hexdigest() for filename, data in book.assets.items()
            },
        )

    def where_deployed(self, source: str, content_id: str, version: str) -> list[int]:
        """Cursos cuyo despliegue actual de ``(source, content_id)`` es ``version``."""
        latest_by_course: dict[int, DeployRecord] = {}
        for record in self._deploys:
            if record.source != source or record.content_id != content_id:
                continue
            previous = latest_by_course.get(record.courseid)
            if previous is None or (record.deployed_at, record.id or 0) > (
                previous.deployed_at,
                previous.id or 0,
            ):
                latest_by_course[record.courseid] = record
        return sorted(
            courseid
            for courseid, record in latest_by_course.items()
            if record.content_version == version
        )

    # -- introspección para tests -------------------------------------------------

    def chapter_titles_in_order(self, bookid: int) -> list[str]:
        """Títulos de capítulo ordenados por position (como se vería en Moodle)."""
        book = self._require_book(bookid, "fake.chapter_titles_in_order")
        ordered = sorted(book.chapters.items(), key=lambda item: item[1].position)
        return [chapter.title for _, chapter in ordered]

    def chapter_html(self, bookid: int, stable_id: str) -> str:
        """HTML actual de un capítulo (asserts de estado tras deploy)."""
        book = self._require_book(bookid, "fake.chapter_html")
        try:
            return book.chapters[stable_id].html
        except KeyError:
            msg = f"fake.chapter_html: el Book {bookid} no tiene el capítulo {stable_id!r}"
            raise MoodleError(msg) from None

    def mutate_chapter(self, bookid: int, stable_id: str, html: str) -> None:
        """Simula la edición manual de un capítulo desde Moodle (drift, §19.1)."""
        book = self._require_book(bookid, "fake.mutate_chapter")
        try:
            chapter = book.chapters[stable_id]
        except KeyError:
            msg = f"fake.mutate_chapter: el Book {bookid} no tiene el capítulo {stable_id!r}"
            raise MoodleError(msg) from None
        book.chapters[stable_id] = RemoteChapter(
            title=chapter.title, html=html, position=chapter.position, url=chapter.url
        )

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
