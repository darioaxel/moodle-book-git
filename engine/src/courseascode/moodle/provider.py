"""Interfaz ``MoodleProvider``: abstracción de Moodle del engine (ENG-060).

El engine nunca habla con Moodle directamente fuera de esta interfaz y sus
implementaciones. ``MoodleRestClient`` (httpx) cubre Moodle real vía web
services del plugin ``local_courseascode``; ``FakeMoodleProvider`` permite
testear el deployment engine sin Moodle.

Contrato del plugin (§5.3b de la spec, fuente de verdad en
``courseascode.moodle.functions``):

```text
local_courseascode_upsert_book(courseid, name, intro, numbering) → bookid
local_courseascode_upsert_chapter(bookid, chapter_stable_id, title, content_html, position)
local_courseascode_delete_chapter(bookid, chapter_stable_id)
local_courseascode_upload_asset(bookid, filename, data) → pluginfile URL
local_courseascode_register_deploy(...)   # todos los campos de la tabla
local_courseascode_get_deploy(courseid, content_id)
```

Los capítulos se identifican por su ``id`` estable del ``book.yml`` (idempotencia,
§17.3); el Book por ``(courseid, source, content_id)`` en la tabla de despliegues.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import TypedDict

from pydantic import BaseModel, ConfigDict, Field

from courseascode.domain.content import Numbering


class MoodleCourse(TypedDict):
    """Curso Moodle tal como lo devuelve ``core_course_get_courses``."""

    id: int
    fullname: str
    shortname: str


class DeployRecord(BaseModel):
    """Fila de la tabla ``local_courseascode_deploy`` (§5.3a de la spec).

    Es el registro de "qué se desplegó, dónde y desde dónde": identidad del
    Book por ``(courseid, source, content_id)``, procedencia Git y
    ``content_hash`` del HTML desplegado (detección de drift, §19.1).
    """

    model_config = ConfigDict(frozen=True)

    courseid: int = Field(description="ID del curso Moodle")
    bookid: int = Field(description="ID del módulo Book en Moodle")
    source: str = Field(min_length=1, description="Fuente del contenido (repo/rama)")
    content_id: str = Field(min_length=1, description="ID estable del Book (book.yml)")
    content_version: str = Field(min_length=1, description="SemVer desplegado")
    git_ref: str = Field(min_length=1, description="Tag, rama o commit desplegado")
    git_commit: str = Field(min_length=1, description="SHA completo del commit")
    content_hash: str = Field(min_length=1, description="Hash del HTML desplegado")
    deployed_at: datetime = Field(description="Fecha de despliegue (ISO 8601)")
    deployed_by: str = Field(min_length=1, description="Usuario que desplegó")
    status: str = Field(default="success", description="Estado del despliegue")
    id: int | None = Field(default=None, description="ID de la fila (lo asigna el plugin)")


class MoodleError(RuntimeError):
    """Error del lado Moodle: web service rechazado, función inexistente, red agotada.

    El mensaje es accionable: incluye el ``errorcode``/``exception`` que devuelve
    Moodle junto al ``wsfunction`` que falló, p. ej.::

        local_courseascode_upsert_chapter: invalid_book (dml_missing_record_exception):
        no existe un Book con id 99
    """

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class MoodleProvider(ABC):
    """Operaciones Moodle que necesita el engine (ENG-060).

    Toda implementación (REST o fake) debe respetar el contrato del plugin
    §5.3b: upsert idempotente por stable id, eliminación por stable id y
    registro/lectura de despliegues por ``(courseid, source, content_id)``.
    """

    @abstractmethod
    def get_course(self, course_id: int) -> MoodleCourse:
        """Devuelve el curso Moodle; ``MoodleError`` si no existe o no es visible."""

    @abstractmethod
    def get_deploy(self, courseid: int, source: str, content_id: str) -> DeployRecord | None:
        """Último despliegue del Book ``(courseid, source, content_id)``; ``None`` si no hay."""

    @abstractmethod
    def upsert_book(self, courseid: int, name: str, intro: str, numbering: Numbering) -> int:
        """Crea o actualiza el Book del curso; devuelve el ``bookid`` (idempotente)."""

    @abstractmethod
    def upsert_chapter(
        self,
        bookid: int,
        chapter_stable_id: str,
        title: str,
        content_html: str,
        position: int,
    ) -> None:
        """Crea o actualiza el capítulo por su ``id`` estable (no duplica al repetir)."""

    @abstractmethod
    def delete_chapter(self, bookid: int, chapter_stable_id: str) -> None:
        """Elimina el capítulo por su ``id`` estable (§17.2: solo tras confirmación)."""

    @abstractmethod
    def upload_asset(self, bookid: int, filename: str, data: bytes) -> str:
        """Sube un asset al Book; devuelve la URL ``pluginfile`` definitiva."""

    @abstractmethod
    def register_deploy(self, record: DeployRecord) -> int:
        """Registra el despliegue en ``local_courseascode_deploy``; devuelve el ID de fila."""

    @abstractmethod
    def list_deploys(self, courseid: int) -> list[DeployRecord]:
        """Todos los despliegues registrados en el curso (más reciente primero)."""
