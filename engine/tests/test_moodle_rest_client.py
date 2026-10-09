"""Tests unitarios de ``MoodleRestClient`` (ENG-061), sin red real.

Toda la HTTP va sobre ``httpx.MockTransport`` (inyectable por ``client=``):
protocolo REST de Moodle, parseo de respuestas, ``MoodleError`` con errorcode,
retries solo ante ``httpx.TransportError`` y backoff desactivable en tests.
"""

from __future__ import annotations

import base64
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest

from courseascode.domain.content import Numbering
from courseascode.moodle import (
    PLUGIN_FUNCTIONS,
    DeployRecord,
    MoodleError,
    MoodleRestClient,
    RetryPolicy,
)

BASE_URL = "https://moodle.example.com"
TOKEN = "wstoken-de-prueba"
BOOKID = 7
DEPLOY_ROW_ID = 3
THREE_ATTEMPTS = 3


def _client(handler: Callable[[httpx.Request], httpx.Response]) -> MoodleRestClient:
    http = httpx.Client(transport=httpx.MockTransport(handler), base_url=BASE_URL)
    return MoodleRestClient(BASE_URL, TOKEN, retries=RetryPolicy.disabled(), client=http)


def _ok(payload: Any) -> httpx.Response:
    return httpx.Response(200, json=payload)


class TestProtocolo:
    def test_parametros_comunes_y_de_funcion(self) -> None:
        captured: dict[str, str] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured.update(dict(request.url.params))
            assert request.method == "POST"
            assert request.url.path == "/webservice/rest/server.php"
            return _ok({"bookid": BOOKID})

        client = _client(handler)
        bookid = client.upsert_book(5, "UT03", "<p>i</p>", Numbering.NUMBERS)

        assert bookid == BOOKID
        assert captured["wstoken"] == TOKEN
        assert captured["wsfunction"] == "local_courseascode_upsert_book"
        assert captured["moodlewsrestformat"] == "json"
        assert captured["courseid"] == "5"
        assert captured["name"] == "UT03"
        assert captured["numbering"] == "numbers"

    def test_url_base_con_trailing_slash(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            assert str(request.url).startswith("https://moodle.example.com/webservice/")
            return _ok({"bookid": BOOKID})

        http = httpx.Client(
            transport=httpx.MockTransport(handler), base_url="https://moodle.example.com/"
        )
        client = MoodleRestClient("https://moodle.example.com/", TOKEN, client=http)
        assert client.upsert_book(5, "UT03", "<p>i</p>", Numbering.NUMBERS) == BOOKID

    def test_get_course_core(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            assert dict(request.url.params)["wsfunction"] == "core_course_get_courses"
            assert dict(request.url.params)["options[ids][0]"] == "42"
            return _ok([{"id": 42, "fullname": "DWES", "shortname": "dwes26"}])

        client = _client(handler)
        course = client.get_course(42)
        assert course == {"id": 42, "fullname": "DWES", "shortname": "dwes26"}

    def test_get_course_no_encontrado(self) -> None:
        client = _client(lambda request: _ok([]))
        with pytest.raises(MoodleError, match="curso no encontrado"):
            client.get_course(42)

    def test_upload_asset_envia_base64_y_parsea_url(self) -> None:
        captured: dict[str, str] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured.update(dict(request.url.params))
            return _ok(
                {"url": "https://moodle.example.com/pluginfile.php/5/mod_book/chapter/x.png"}
            )

        client = _client(handler)
        url = client.upload_asset(5, "x.png", b"\x89PNG")

        assert captured["data"] == base64.b64encode(b"\x89PNG").decode("ascii")
        assert url.endswith("/x.png")

    def test_get_deploy_null_y_registro(self) -> None:
        calls: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            params = dict(request.url.params)
            calls.append(params["wsfunction"])
            if params["wsfunction"] == "local_courseascode_get_deploy":
                return httpx.Response(
                    200, content=b"null", headers={"Content-Type": "application/json"}
                )
            return _ok({"id": DEPLOY_ROW_ID})

        client = _client(handler)
        assert client.get_deploy(5, "main", "ut03-mvc") is None

        record = DeployRecord(
            courseid=5,
            bookid=BOOKID,
            source="main",
            content_id="ut03-mvc",
            content_version="1.2.0",
            git_ref="book/ut03-mvc/v1.2.0",
            git_commit="a" * 40,
            content_hash="sha256:" + "b" * 64,
            deployed_at=datetime(2026, 1, 15, 10, 30, tzinfo=UTC),
            deployed_by="coordinador",
        )
        assert client.register_deploy(record) == DEPLOY_ROW_ID
        assert calls == ["local_courseascode_get_deploy", "local_courseascode_register_deploy"]

    def test_list_deploys_parsea_records(self) -> None:
        fila: dict[str, Any] = {
            "id": 1,
            "courseid": 5,
            "bookid": BOOKID,
            "source": "main",
            "content_id": "ut03-mvc",
            "content_version": "1.2.0",
            "git_ref": "book/ut03-mvc/v1.2.0",
            "git_commit": "a" * 40,
            "content_hash": "sha256:" + "b" * 64,
            "deployed_at": "2026-01-15T10:30:00+00:00",
            "deployed_by": "coordinador",
            "status": "success",
        }

        client = _client(lambda request: _ok([fila]))
        records = client.list_deploys(5)
        assert len(records) == 1
        assert records[0].content_version == "1.2.0"
        assert records[0].deployed_at == datetime(2026, 1, 15, 10, 30, tzinfo=UTC)


class TestErroresMoodle:
    def test_error_moodle_con_errorcode_y_exception(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return _ok(
                {
                    "exception": "dml_missing_record_exception",
                    "errorcode": "invalid_book",
                    "message": "No existe un Book con id 99",
                }
            )

        client = _client(handler)
        with pytest.raises(MoodleError) as exc_info:
            client.upsert_chapter(99, "intro", "Intro", "<h1>i</h1>", 1)

        message = str(exc_info.value)
        assert "invalid_book" in message
        assert "dml_missing_record_exception" in message
        assert "No existe un Book con id 99" in message
        assert "upsert_chapter" in message

    def test_error_moodle_no_se_reintenta(self) -> None:
        attempts = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal attempts
            attempts += 1
            return _ok({"exception": "moodle_exception", "errorcode": "nop", "message": "no"})

        http = httpx.Client(transport=httpx.MockTransport(handler), base_url=BASE_URL)
        client = MoodleRestClient(
            BASE_URL, TOKEN, retries=RetryPolicy(attempts=THREE_ATTEMPTS), client=http
        )
        with pytest.raises(MoodleError):
            client.upsert_book(5, "UT03", "<p>i</p>", Numbering.NUMBERS)
        assert attempts == 1

    def test_respuesta_no_json(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text="<html>login</html>")

        client = _client(handler)
        with pytest.raises(MoodleError, match="no-JSON"):
            client.get_course(1)

    def test_http_4xx_sin_json_de_moodle(self) -> None:
        client = _client(lambda request: httpx.Response(500, text="boom"))
        with pytest.raises(MoodleError, match="HTTP 500"):
            client.get_course(1)

    def test_respuesta_inesperada_en_upsert_book(self) -> None:
        client = _client(lambda request: _ok({"unexpected": True}))
        with pytest.raises(MoodleError, match="bookid"):
            client.upsert_book(5, "UT03", "<p>i</p>", Numbering.NUMBERS)


class TestRetries:
    def test_reintenta_solo_fallos_de_red(self) -> None:
        attempts = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal attempts
            attempts += 1
            if attempts < THREE_ATTEMPTS:
                raise httpx.ConnectError("conexión rechazada")
            return _ok({"bookid": BOOKID})

        http = httpx.Client(transport=httpx.MockTransport(handler), base_url=BASE_URL)
        client = MoodleRestClient(
            BASE_URL, TOKEN, retries=RetryPolicy(attempts=THREE_ATTEMPTS), client=http
        )
        assert client.upsert_book(5, "UT03", "<p>i</p>", Numbering.NUMBERS) == BOOKID
        assert attempts == THREE_ATTEMPTS

    def test_agota_reintentos_y_propaga_moodle_error(self) -> None:
        attempts = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal attempts
            attempts += 1
            raise httpx.ReadTimeout("timeout")

        http = httpx.Client(transport=httpx.MockTransport(handler), base_url=BASE_URL)
        client = MoodleRestClient(
            BASE_URL, TOKEN, retries=RetryPolicy(attempts=THREE_ATTEMPTS), client=http
        )
        with pytest.raises(MoodleError, match="error de red tras 3 intentos"):
            client.upsert_book(5, "UT03", "<p>i</p>", Numbering.NUMBERS)
        assert attempts == THREE_ATTEMPTS

    def test_backoff_aplicado_y_desactivable(self) -> None:
        sleeps: list[float] = []
        attempts = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal attempts
            attempts += 1
            raise httpx.ConnectError("x")

        http = httpx.Client(transport=httpx.MockTransport(handler), base_url=BASE_URL)
        client = MoodleRestClient(
            BASE_URL,
            TOKEN,
            retries=RetryPolicy(attempts=THREE_ATTEMPTS, backoff_seconds=(0.2, 0.5)),
            client=http,
        )
        client._sleep = sleeps.append
        with pytest.raises(MoodleError):
            client.upsert_book(5, "UT03", "<p>i</p>", Numbering.NUMBERS)
        assert sleeps == [0.2, 0.5]
        assert attempts == THREE_ATTEMPTS

    def test_retries_1_desactiva_reintentos(self) -> None:
        attempts = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal attempts
            attempts += 1
            raise httpx.ConnectError("x")

        client = _client(handler)
        with pytest.raises(MoodleError):
            client.get_course(1)
        assert attempts == 1

    def test_rechaza_intentos_invalidos(self) -> None:
        with pytest.raises(ValueError, match="attempts"):
            RetryPolicy(attempts=0)


def test_mapeo_funciones_cubre_operaciones() -> None:
    esperadas = {
        "get_course",
        "upsert_book",
        "upsert_chapter",
        "delete_chapter",
        "upload_asset",
        "register_deploy",
        "get_deploy",
        "list_deploys",
    }
    assert esperadas <= set(PLUGIN_FUNCTIONS)
    for key, function in PLUGIN_FUNCTIONS.items():
        if key != "get_course":
            assert function.name.startswith("local_courseascode_")
