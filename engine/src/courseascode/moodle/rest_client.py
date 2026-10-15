"""``MoodleRestClient``: implementación HTTP de ``MoodleProvider`` (ENG-061).

Cliente del protocolo REST de los web services de Moodle sobre ``httpx``:

- POST a ``{base_url}/webservice/rest/server.php`` con los parámetros comunes
  ``wstoken``, ``wsfunction``, ``moodlewsrestformat=json`` más los parámetros
  de cada función (el mapeo documentado está en ``courseascode.moodle.functions``).
- Errores de Moodle: respuesta JSON con ``exception``/``errorcode``/``message``
  → ``MoodleError`` con mensaje accionable. Un error de Moodle válido **no se
  reintenta**: se propaga tal cual.
- Retries con backoff **solo en fallos de red** (``httpx.TransportError``:
  conexión rechazada, timeout), configurables con ``RetryPolicy``. Se
  desactivan con ``RetryPolicy.disabled()``.

El cliente ``httpx`` es inyectable para tests (``MockTransport``) vía ``client=``.
"""

from __future__ import annotations

import base64
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import httpx

from courseascode.domain.content import Numbering
from courseascode.moodle.functions import PLUGIN_FUNCTIONS
from courseascode.moodle.provider import (
    DeployRecord,
    MoodleCourse,
    MoodleError,
    MoodleProvider,
    RemoteBook,
    RemoteChapter,
)

DEFAULT_RETRIES = 3
DEFAULT_BACKOFF_SECONDS: tuple[float, ...] = (0.2, 0.5, 1.0)
HTTP_ERROR_STATUS = 400


@dataclass(frozen=True)
class RetryPolicy:
    """Reintentos ante fallos de red: ``attempts`` intentos con esperas ``backoff_seconds``."""

    attempts: int = DEFAULT_RETRIES
    backoff_seconds: tuple[float, ...] = DEFAULT_BACKOFF_SECONDS

    def __post_init__(self) -> None:
        if self.attempts < 1:
            msg = "attempts debe ser >= 1 (un intento mínimo)"
            raise ValueError(msg)

    @classmethod
    def disabled(cls) -> RetryPolicy:
        """Sin reintentos ni esperas (tests y entornos donde fallar rápido importa)."""
        return cls(attempts=1, backoff_seconds=())


class MoodleRestClient(MoodleProvider):
    """Habla con Moodle real a través de los web services del plugin (ENG-061)."""

    def __init__(
        self,
        base_url: str,
        token: str,
        *,
        timeout: float = 10.0,
        retries: RetryPolicy | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        self._token = token
        self._retry = retries or RetryPolicy()
        self._client = client or httpx.Client(base_url=base_url.rstrip("/"), timeout=timeout)
        self._sleep: Callable[[float], None] = time.sleep

    # -- núcleo HTTP --------------------------------------------------------------

    def _call(self, wsfunction: str, **params: Any) -> Any:
        """Invoca un wsfunction con reintentos solo ante fallos de red."""
        payload: dict[str, Any] = {
            "wstoken": self._token,
            "wsfunction": wsfunction,
            "moodlewsrestformat": "json",
            **params,
        }
        attempts = self._retry.attempts
        last_error: httpx.TransportError | None = None
        for attempt in range(1, attempts + 1):
            try:
                response = self._client.post("/webservice/rest/server.php", params=payload)
            except httpx.TransportError as exc:
                last_error = exc
                if attempt < attempts:
                    backoff = self._retry.backoff_seconds
                    self._sleep(backoff[min(attempt - 1, len(backoff) - 1)])
                    continue
                msg = f"{wsfunction}: error de red tras {attempts} intentos contra Moodle: {exc}"
                raise MoodleError(msg) from exc
            return self._parse(response, wsfunction)
        msg = f"{wsfunction}: imposible (sin intentos)"
        raise MoodleError(msg) from last_error

    @staticmethod
    def _parse(response: httpx.Response, wsfunction: str) -> Any:
        """Extrae el JSON de la respuesta, convirtiendo errores de Moodle en MoodleError."""
        try:
            data: Any = response.json()
        except ValueError:
            msg = (
                f"{wsfunction}: respuesta no-JSON de Moodle"
                f" (HTTP {response.status_code}): {response.text[:200]}"
            )
            raise MoodleError(msg) from None
        if isinstance(data, dict) and "exception" in data:
            errorcode = data.get("errorcode", "unknown")
            exception = data.get("exception", "")
            detail = data.get("message", "sin mensaje")
            msg = f"{wsfunction}: {errorcode} ({exception}): {detail}"
            raise MoodleError(msg)
        if response.status_code >= HTTP_ERROR_STATUS:
            msg = f"{wsfunction}: HTTP {response.status_code}: {str(data)[:200]}"
            raise MoodleError(msg)
        return data

    # -- MoodleProvider ------------------------------------------------------------

    def get_course(self, course_id: int) -> MoodleCourse:
        name = PLUGIN_FUNCTIONS["get_course"].name
        data = self._call(name, **{"options[ids][0]": course_id})
        courses = data if isinstance(data, list) else [data]
        for course in courses:
            if isinstance(course, dict) and course.get("id") == course_id:
                return {
                    "id": int(course["id"]),
                    "fullname": str(course.get("fullname", "")),
                    "shortname": str(course.get("shortname", "")),
                }
        msg = f"{name}: curso no encontrado o no visible para el token: {course_id}"
        raise MoodleError(msg)

    def get_deploy(self, courseid: int, source: str, content_id: str) -> DeployRecord | None:
        name = PLUGIN_FUNCTIONS["get_deploy"].name
        data = self._call(name, courseid=courseid, source=source, content_id=content_id)
        if data in (None, {}, []):
            return None
        return DeployRecord.model_validate(data)

    def upsert_book(self, courseid: int, name: str, intro: str, numbering: Numbering) -> int:
        ws = PLUGIN_FUNCTIONS["upsert_book"].name
        data = self._call(ws, courseid=courseid, name=name, intro=intro, numbering=str(numbering))
        return self._require_int(ws, data, "bookid")

    def upsert_chapter(
        self,
        bookid: int,
        chapter_stable_id: str,
        title: str,
        content_html: str,
        position: int,
    ) -> None:
        ws = PLUGIN_FUNCTIONS["upsert_chapter"].name
        self._call(
            ws,
            bookid=bookid,
            chapter_stable_id=chapter_stable_id,
            title=title,
            content_html=content_html,
            position=position,
        )

    def delete_chapter(self, bookid: int, chapter_stable_id: str) -> None:
        ws = PLUGIN_FUNCTIONS["delete_chapter"].name
        self._call(ws, bookid=bookid, chapter_stable_id=chapter_stable_id)

    def upload_asset(self, bookid: int, filename: str, data: bytes) -> str:
        ws = PLUGIN_FUNCTIONS["upload_asset"].name
        payload = base64.b64encode(data).decode("ascii")
        result = self._call(ws, bookid=bookid, filename=filename, data=payload)
        if not isinstance(result, dict):
            msg = f"{ws}: respuesta inesperada (se esperaba {{'url': str}}): {result!r}"
            raise MoodleError(msg)
        url = result.get("url")
        if not isinstance(url, str):
            msg = f"{ws}: respuesta inesperada (se esperaba {{'url': str}}): {result!r}"
            raise MoodleError(msg)
        return url

    def register_deploy(self, record: DeployRecord) -> int:
        ws = PLUGIN_FUNCTIONS["register_deploy"].name
        data = self._call(
            ws,
            courseid=record.courseid,
            bookid=record.bookid,
            source=record.source,
            content_id=record.content_id,
            content_version=record.content_version,
            git_ref=record.git_ref,
            git_commit=record.git_commit,
            content_hash=record.content_hash,
            deployed_at=record.deployed_at.isoformat(),
            deployed_by=record.deployed_by,
            status=record.status,
        )
        return self._require_int(ws, data, "id")

    def list_deploys(self, courseid: int) -> list[DeployRecord]:
        ws = PLUGIN_FUNCTIONS["list_deploys"].name
        data = self._call(ws, courseid=courseid)
        if isinstance(data, dict):
            data = data.get("deploys", [])
        if not isinstance(data, list):
            msg = f"{ws}: respuesta inesperada (se esperaba lista): {data!r}"
            raise MoodleError(msg)
        return [DeployRecord.model_validate(item) for item in data]

    def get_book(self, bookid: int) -> RemoteBook | None:
        """Estado actual del Book: metadatos, capítulos y assets (ENG-074)."""
        ws = PLUGIN_FUNCTIONS["get_book"].name
        data = self._call(ws, bookid=bookid)
        if data in (None, {}, []):
            return None
        if not isinstance(data, dict):
            msg = f"{ws}: respuesta inesperada (se esperaba objeto): {data!r}"
            raise MoodleError(msg)
        try:
            chapters = {
                str(item["stable_id"]): RemoteChapter(
                    title=str(item["title"]),
                    html=str(item["content_html"]),
                    position=int(item["position"]),
                    url=str(item["url"]),
                )
                for item in data.get("chapters", [])
            }
            assets = {str(item["filename"]): str(item["sha256"]) for item in data.get("assets", [])}
            return RemoteBook(
                bookid=int(data["bookid"]),
                courseid=int(data["courseid"]),
                name=str(data["name"]),
                intro=str(data.get("intro", "")),
                numbering=Numbering(str(data.get("numbering", "numbers"))),
                chapters=chapters,
                assets=assets,
            )
        except (KeyError, TypeError, ValueError) as exc:
            msg = f"{ws}: respuesta inesperada (falta campo o tipo incorrecto): {exc}"
            raise MoodleError(msg) from exc

    def where_deployed(self, source: str, content_id: str, version: str) -> list[int]:
        """Cursos con ``version`` como despliegue actual de ``(source, content_id)``."""
        ws = PLUGIN_FUNCTIONS["where_deployed"].name
        data = self._call(ws, source=source, content_id=content_id, version=version)
        courseids = data.get("courseids", []) if isinstance(data, dict) else data
        if not isinstance(courseids, list):
            msg = f"{ws}: respuesta inesperada (se esperaba lista): {data!r}"
            raise MoodleError(msg)
        return [int(item) for item in courseids]

    @staticmethod
    def _require_int(wsfunction: str, data: Any, key: str) -> int:
        value = data.get(key) if isinstance(data, dict) else None
        if isinstance(value, int):
            return value
        msg = f"{wsfunction}: respuesta inesperada (se esperaba {{{key!r}: int}}): {data!r}"
        raise MoodleError(msg)
