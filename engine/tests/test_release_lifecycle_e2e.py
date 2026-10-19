"""DoD de Fase 8 (§11): ciclo completo hotfix crítico contra el fake.

Deploy de una versión → marcarla ``critical`` + ``--recall`` → ``status``
muestra el badge crítico → redeploy de la versión recallada falla sin
``--force`` y pasa con ``--force`` (con warning) → ``/deployment/where`` y
``/releases/affected`` listan el curso afectado. Un solo servicio con el
``SqlReleasePort`` real sobre SQLite: es el circuito que la Fase 8 cierra
sin tocar planner/executor.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from courseascode.deployment import DeploymentService, RecalledVersionError
from courseascode.domain.deployment import DeploymentState, Severity
from courseascode.git import LocalGitProvider
from courseascode.moodle import FakeMoodleProvider
from courseascode.releases import ReleaseStore, SqlReleasePort
from courseascode.web import create_app

COURSE = 2026
OTHER_COURSE = 2027
SOURCE = "dwes"
BOOK = "ut03-mvc"
VERSION = "1.0.0"

HTTP_OK = 200
TWO_DEPLOYS = 2


def test_dod_fase8_hotfix_critico(git_repo: Path, tmp_path: Path) -> None:
    fake = FakeMoodleProvider(course_ids=(COURSE, OTHER_COURSE))
    store = ReleaseStore(f"sqlite:///{tmp_path / 'dod.db'}")
    service = DeploymentService(
        LocalGitProvider(git_repo), fake, SqlReleasePort(store, source=SOURCE), source=SOURCE
    )

    # 1. Deploy inicial de la versión (en dos cursos).
    service.deploy(COURSE, BOOK, version=VERSION, assume_yes=True)
    service.deploy(OTHER_COURSE, BOOK, version=VERSION, assume_yes=True, deployed_by="profe-b")

    # 2. El coordinador declara la severidad (flujo §11.1, como `release mark`).
    store.mark(
        f"book/{BOOK}/v{VERSION}",
        source=SOURCE,
        severity=Severity.CRITICAL,
        recalled=True,
        fixed_in="1.2.0",
        reason="Contenido erróneo detectado tras la publicación",
        marked_by="coordinator",
    )

    # 3. `status` muestra el badge crítico para quien ya la tiene desplegada.
    rows = service.course_status(COURSE)
    assert len(rows) == 1
    assert rows[0].state.state is DeploymentState.UPDATE_AVAILABLE  # hay 1.2.0 nueva
    assert rows[0].state.severity is Severity.CRITICAL

    # 4. Redeploy de la versión RECALLED falla; con --force pasa y avisa.
    with pytest.raises(RecalledVersionError, match="RECALLED"):
        service.deploy(COURSE, BOOK, version=VERSION, assume_yes=True)
    # Drift manual (§19.1): sin él el redeploy forzado no tendría acciones.
    record = fake.get_deploy(COURSE, SOURCE, BOOK)
    assert record is not None
    fake.mutate_chapter(record.bookid, "model", "<h1>Model EDITADO A MANO</h1>")
    forced = service.deploy(COURSE, BOOK, version=VERSION, assume_yes=True, force=True)
    assert forced.success
    assert any("RECALLED" in warning for warning in forced.warnings)

    # 5. La consulta inversa lista los cursos afectados…
    assert service.where(SOURCE, BOOK, VERSION) == [COURSE, OTHER_COURSE]

    # 6. …y el endpoint de afectados da el detalle para la notificación 🔌.
    app = create_app(
        git_repo,
        provider=LocalGitProvider(git_repo),
        moodle=fake,
        store=store,
        admin_token="admin",
    )
    response = TestClient(app).get(
        f"/releases/affected?source={SOURCE}&book={BOOK}&version={VERSION}"
    )
    assert response.status_code == HTTP_OK
    data = response.json()
    assert data["marked"] is True
    assert {item["course_id"] for item in data["affected"]} == {COURSE, OTHER_COURSE}
    by_course = {item["course_id"]: item for item in data["affected"]}
    assert by_course[COURSE]["severity"] == "critical"
    assert by_course[COURSE]["recalled"] is True
    assert by_course[COURSE]["fixed_in"] == "1.2.0"
    assert by_course[COURSE]["deployed_by"] == "api"  # proxy de "profesor"
    assert by_course[OTHER_COURSE]["deployed_by"] == "profe-b"

    # 7. Todo el ciclo queda en auditoría (deploys + mark).
    events = store.audit()
    types = [event.event_type for event in events]
    assert types.count("deploy") >= TWO_DEPLOYS
    assert "release.mark" in types
