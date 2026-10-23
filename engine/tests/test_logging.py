"""Tests del logging estructurado y el correlation id (ENG-101)."""

from __future__ import annotations

from collections.abc import Iterator, MutableMapping
from pathlib import Path
from typing import Any

import pytest
import structlog
from structlog import contextvars as structlog_contextvars

from courseascode.deployment.service import DeploymentService
from courseascode.git import GitProviderError, LocalGitProvider
from courseascode.logging_config import (
    bound_correlation,
    correlation_id,
    new_correlation_id,
)
from courseascode.moodle import FakeMoodleProvider

COURSE = 101
BOOK = "ut03-mvc"


@pytest.fixture()
def service(git_repo: Path) -> DeploymentService:
    fake = FakeMoodleProvider()
    fake.add_course(COURSE, "DWES")
    return DeploymentService(LocalGitProvider(git_repo), fake)


@pytest.fixture()
def captured() -> Iterator[list[dict[str, Any]]]:
    """structlog reconfigurado con merge de contextvars + procesador capturador.

    ``structlog.testing.capture_logs`` no sirve aquí: descarta los processors
    configurados y el correlation id llega vía ``merge_contextvars``.
    """
    events: list[dict[str, Any]] = []

    def _capture(logger: Any, method: str, event_dict: MutableMapping[str, Any]) -> dict[str, Any]:
        captured_dict = dict(event_dict)
        events.append(captured_dict)
        return captured_dict

    structlog.configure(
        processors=[structlog_contextvars.merge_contextvars, _capture],
        wrapper_class=structlog.BoundLogger,
        logger_factory=structlog.ReturnLoggerFactory(),
        cache_logger_on_first_use=False,
    )
    yield events
    structlog.reset_defaults()


def test_correlation_id_se_propaga_a_todos_los_eventos_del_deploy(
    service: DeploymentService, captured: list[dict[str, Any]]
) -> None:
    service.deploy(COURSE, BOOK, version="1.0.0", assume_yes=True)
    events = [e for e in captured if e["event"].startswith("deploy.")]
    kinds = {e["event"] for e in events}
    assert {"deploy.start", "deploy.plan", "deploy.execute"} <= kinds
    cids = {e["correlation_id"] for e in events}
    assert len(cids) == 1
    assert cids != {None}


def test_deploys_distintos_llevan_correlation_ids_distintos(
    service: DeploymentService, captured: list[dict[str, Any]]
) -> None:
    service.deploy(COURSE, BOOK, version="1.0.0", assume_yes=True)
    cid_one = {e["correlation_id"] for e in captured if e["event"] == "deploy.start"}
    captured.clear()
    service.deploy(COURSE, BOOK, version="1.1.0", assume_yes=True)
    cid_two = {e["correlation_id"] for e in captured if e["event"] == "deploy.start"}
    assert len(cid_one) == len(cid_two) == 1
    assert cid_one != cid_two


def test_fallo_de_deploy_tambien_lleva_correlation_id(
    service: DeploymentService, captured: list[dict[str, Any]]
) -> None:
    with pytest.raises(GitProviderError):
        service.deploy(COURSE, "ut99-desconocido", version="1.0.0", assume_yes=True)
    errors = [e for e in captured if e["event"] == "deploy.error"]
    assert errors
    assert all(e["correlation_id"] for e in errors)


def test_bound_correlation_fija_y_resetea_la_contextvar() -> None:
    assert correlation_id.get() is None
    with bound_correlation("abc12345") as cid:
        assert cid == "abc12345"
        assert correlation_id.get() == "abc12345"
    assert correlation_id.get() is None


CID_LENGTH = 8


def test_bound_correlation_genera_id_corto_cuando_no_llega() -> None:
    assert len(new_correlation_id()) == CID_LENGTH
    with bound_correlation() as cid:
        assert len(cid) == CID_LENGTH
        assert correlation_id.get() == cid
