"""Tests de contrato de ``MoodleProvider`` (ENG-064).

Los mismos casos corren contra:

- ``FakeMoodleProvider`` (siempre): valida que el fake reproduce el contrato.
- ``MoodleRestClient`` contra Moodle real (mark ``integration``, se salta con
  ``pytest.mark.skipif`` si no hay ``MOODLE_URL``/``MOODLE_TOKEN`` de un
  moodle-docker con el plugin ``local_courseascode``).

Un test que use el provider mediante esta suite pasa indistintamente contra
fake y Moodle real (DoD Fase 6).
"""

from __future__ import annotations

import os
from collections.abc import Callable, Iterator
from datetime import UTC, datetime

import httpx
import pytest

from courseascode.domain.content import Numbering
from courseascode.moodle import (
    DeployRecord,
    FakeMoodleProvider,
    MoodleError,
    MoodleProvider,
    MoodleRestClient,
    RetryPolicy,
)

COURSE_ID = 101
SOURCE = "main"
CONTENT_ID = "ut03-mvc"

_MOODLE_CONFIGURED = bool(os.environ.get("MOODLE_URL") and os.environ.get("MOODLE_TOKEN"))
_skip_sin_moodle = pytest.mark.skipif(
    not _MOODLE_CONFIGURED,
    reason="requiere MOODLE_URL/MOODLE_TOKEN de moodle-docker con local_courseascode",
)


def _build_fake() -> MoodleProvider:
    fake = FakeMoodleProvider()
    fake.add_course(COURSE_ID, "DWES 2026-2027", "DWES")
    return fake


def _build_rest() -> MoodleProvider:
    return MoodleRestClient(
        base_url=os.environ["MOODLE_URL"],
        token=os.environ["MOODLE_TOKEN"],
        retries=RetryPolicy.disabled(),
    )


_FACTORIES = [
    pytest.param(_build_fake, id="fake"),
    pytest.param(
        _build_rest,
        marks=[pytest.mark.integration, _skip_sin_moodle],
        id="moodle",
    ),
]


@pytest.fixture(params=_FACTORIES)
def moodle(request: pytest.FixtureRequest) -> Iterator[MoodleProvider]:
    factory: Callable[[], MoodleProvider] = request.param
    provider = factory()
    yield provider
    client = getattr(provider, "_client", None)
    if isinstance(client, httpx.Client):
        client.close()


def _sample_record(bookid: int, *, version: str = "1.2.0", commit: str = "a" * 40) -> DeployRecord:
    return DeployRecord(
        courseid=COURSE_ID,
        bookid=bookid,
        source=SOURCE,
        content_id=CONTENT_ID,
        content_version=version,
        git_ref=f"book/{CONTENT_ID}/v{version}",
        git_commit=commit,
        content_hash="sha256:" + "b" * 64,
        deployed_at=datetime(2026, 1, 15, 10, 30, tzinfo=UTC),
        deployed_by="tester",
        status="success",
    )


class TestContratoMoodle:
    def test_get_course(self, moodle: MoodleProvider) -> None:
        course = moodle.get_course(COURSE_ID)
        assert course["id"] == COURSE_ID

    def test_get_course_inexistente(self, moodle: MoodleProvider) -> None:
        with pytest.raises(MoodleError, match="curso"):
            moodle.get_course(999_999)

    def test_upsert_book_idempotente(self, moodle: MoodleProvider) -> None:
        bookid_1 = moodle.upsert_book(COURSE_ID, "UT03 MVC", "<p>Intro</p>", Numbering.NUMBERS)
        bookid_2 = moodle.upsert_book(
            COURSE_ID, "UT03 MVC", "<p>Intro actualizado</p>", Numbering.NUMBERS
        )
        assert bookid_1 == bookid_2

    def test_ciclo_completo(self, moodle: MoodleProvider) -> None:
        moodle.get_course(COURSE_ID)
        bookid = moodle.upsert_book(COURSE_ID, "UT03 MVC", "<p>Intro</p>", Numbering.NUMBERS)

        moodle.upsert_chapter(bookid, "intro", "Introducción", "<h1>Intro</h1>", 1)
        moodle.upsert_chapter(bookid, "mvc", "MVC", "<h1>MVC</h1>", 2)
        moodle.upsert_chapter(bookid, "model", "Model", "<h1>Model</h1>", 3)

        # Repetir upserts no duplica (idempotencia §17.3).
        moodle.upsert_chapter(bookid, "mvc", "MVC", "<h1>MVC v2</h1>", 2)
        if isinstance(moodle, FakeMoodleProvider):
            assert moodle.chapter_titles_in_order(bookid) == ["Introducción", "MVC", "Model"]
            book = moodle.get_book(bookid)
            assert book is not None
            assert book.chapters["mvc"].html == "<h1>MVC v2</h1>"

        url = moodle.upload_asset(bookid, "mvc.svg", b"<svg/>")
        assert url
        assert "mvc.svg" in url

        record = _sample_record(bookid)
        deploy_id = moodle.register_deploy(record)
        assert deploy_id >= 1

        found = moodle.get_deploy(COURSE_ID, SOURCE, CONTENT_ID)
        assert found is not None
        assert found.bookid == bookid
        assert found.content_version == "1.2.0"
        assert found.git_commit == "a" * 40

        listed = moodle.list_deploys(COURSE_ID)
        assert any(r.content_id == CONTENT_ID for r in listed)

        moodle.delete_chapter(bookid, "model")
        if isinstance(moodle, FakeMoodleProvider):
            assert moodle.chapter_titles_in_order(bookid) == ["Introducción", "MVC"]

    def test_get_deploy_sin_despliegue(self, moodle: MoodleProvider) -> None:
        assert moodle.get_deploy(COURSE_ID, SOURCE, "nunca-desplegado") is None

    def test_get_deploy_devuelve_el_mas_reciente(self, moodle: MoodleProvider) -> None:
        bookid = moodle.upsert_book(COURSE_ID, "UT03 MVC", "<p>Intro</p>", Numbering.NUMBERS)
        moodle.register_deploy(
            _sample_record(bookid, version="1.1.0", commit="c" * 40).model_copy(
                update={"deployed_at": datetime(2026, 1, 10, tzinfo=UTC)}
            )
        )
        moodle.register_deploy(
            _sample_record(bookid, version="1.2.0", commit="d" * 40).model_copy(
                update={"deployed_at": datetime(2026, 1, 20, tzinfo=UTC)}
            )
        )
        found = moodle.get_deploy(COURSE_ID, SOURCE, CONTENT_ID)
        assert found is not None
        assert found.content_version == "1.2.0"

    def test_upsert_chapter_bookid_inexistente(self, moodle: MoodleProvider) -> None:
        with pytest.raises(MoodleError, match="invalid_book"):
            moodle.upsert_chapter(999_999, "intro", "Intro", "<h1>Intro</h1>", 1)

    def test_delete_chapter_inexistente(self, moodle: MoodleProvider) -> None:
        bookid = moodle.upsert_book(COURSE_ID, "UT03 MVC", "<p>Intro</p>", Numbering.NUMBERS)
        with pytest.raises(MoodleError, match="chapter_not_found"):
            moodle.delete_chapter(bookid, "no-existe")

    def test_upload_asset_bookid_inexistente(self, moodle: MoodleProvider) -> None:
        with pytest.raises(MoodleError, match="invalid_book"):
            moodle.upload_asset(999_999, "x.png", b"data")

    def test_moodle_error_es_accionable(self, moodle: MoodleProvider) -> None:
        with pytest.raises(MoodleError) as exc_info:
            moodle.upsert_chapter(999_999, "intro", "Intro", "<h1>Intro</h1>", 1)
        message = str(exc_info.value)
        # Mensaje accionable: wsfunction, errorcode y detalle (§ENG-060).
        assert "upsert_chapter" in message
        assert "999999" in message
