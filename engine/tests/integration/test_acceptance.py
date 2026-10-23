"""Suite E2E de los criterios de aceptación de §32 (ENG-104) contra moodle-docker.

Automatiza desde el engine los criterios que son funcionalidad del servicio:

- §32.5-6  ciclo de **importación**: deploy de v1.0.0 → Book creado con
  imágenes visibles (URLs ``pluginfile.php`` reales), enlaces internos
  resueltos y registro ``(source, content_id, version, git_commit)``.
- §32.7-10 ciclo de **actualización**: el *mismo* Book Moodle se actualiza sin
  duplicados y el estado previo era ``UPDATE_AVAILABLE``.
- §32.11   ciclo de **rollback**: redeploy de v1.0.0 reconstruye el Book
  exactamente a ese estado (es el mismo pipeline, §18).
- §32.13   ciclo de **hotfix**: severidad ``critical`` + recall bloquea nuevos
  despliegues de la versión retirada, el estado muestra el badge crítico y la
  consulta inversa lista los cursos afectados.

**Fuera de alcance aquí:**

- §32.1-4 (ciclo básico del autor: ``validate``/``preview``/tag) ya tiene DoD
  propio por fases y no toca Moodle; el tag es requisito de estos tests.
- §32.12 (gobernanza: ``validate`` en verde bloqueante y quórum de
  aprobaciones en PRs) es **gobernanza de la plataforma Git** (GitHub/GitLab:
  branch protection, status checks, CODEOWNERS), no funcionalidad del engine:
  no hay nada que automatizar desde este repo. Se verifica configurando la
  plataforma (guía de operación, §10.2 de la spec).
- La parte de UI de §32.5-10 (catálogo dentro de Moodle, botones) pertenece al
  plugin 🔌 ``local_courseascode``; aquí se verifica el contrato servicio→plugin
  que esos flujos consumen.

Misma mecánica que ``tests/test_moodle_contract.py``: mark ``integration`` +
``skipif`` sin ``MOODLE_URL``/``MOODLE_TOKEN``. Cada test construye su propio
repo de contenidos temporal (curso desechable) y usa ``DeploymentService`` /
``MoodleRestClient`` reales. El curso Moodle es desechable y configurable con
``MOODLE_TEST_COURSEID`` (por defecto ``101``: el ID usado también en la suite
de contrato; créese como curso vacío en el moodle-docker antes de correr la
suite, p. ej. con el CLI de administración ``php admin/cli/...`` o a mano).
"""

from __future__ import annotations

import os
import subprocess
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest

from courseascode.deployment import (
    DeploymentService,
    NullReleasePort,
    RecalledVersionError,
)
from courseascode.domain.deployment import DeploymentState, Severity
from courseascode.git import LocalGitProvider
from courseascode.moodle import MoodleRestClient
from courseascode.releases import ReleaseStore, SqlReleasePort

SOURCE = "dwes"
BOOK_ID = "ut03-mvc"

COURSE_ID = int(os.environ.get("MOODLE_TEST_COURSEID", "101"))
#: Nº de capítulos del Book de prueba (§32 pide 5; 3 bastan para el contrato
#: engine↔Moodle y mantienen la suite ágil).
CHAPTERS = ("01-introduccion.md", "02-mvc.md", "03-model.md")

_MOODLE_CONFIGURED = bool(os.environ.get("MOODLE_URL") and os.environ.get("MOODLE_TOKEN"))
_skip_sin_moodle = pytest.mark.skipif(
    not _MOODLE_CONFIGURED,
    reason="requiere MOODLE_URL/MOODLE_TOKEN de moodle-docker con local_courseascode",
)
pytestmark = [pytest.mark.integration, _skip_sin_moodle]

_COURSE_YML = """\
id: dwes
title: Desarrollo Web en Entorno Servidor

books:
  - id: ut03-mvc
    path: books/ut03-mvc
"""

_BOOK_YML = """\
id: ut03-mvc
type: book

title: MVC y patrones de diseño

description: >
  Introducción al patrón MVC y su aplicación
  en aplicaciones web.

summary: >
  Introducción al patrón MVC y su aplicación
  en aplicaciones web con PHP.
tags: [php, patrones, arquitectura]
audience: 2º DAW · DWES

numbering: numbers

chapters:
  - id: introduccion
    title: Introducción
    file: 01-introduccion.md
  - id: mvc
    title: MVC
    file: 02-mvc.md
  - id: model
    title: Model
    file: 03-model.md
"""

_INTRO_MD = """\
# Introducción

El patrón MVC separa responsabilidades.

![Diagrama MVC](assets/diagrama.svg)

Ver [el capítulo de Model](03-model.md) para el detalle.

:::note
Este book es desechable: lo crea la suite E2E.
:::
"""

_MVC_MD_V1 = """\
# MVC

Modelo, vista y controlador.

Contenido de la versión 1.0.0.
"""

_MVC_MD_V2 = """\
# MVC

Modelo, vista y controlador.

Contenido de la versión 1.1.0 (capítulo actualizado).
"""

_MODEL_MD = """\
# Model

La capa de acceso a datos y reglas de negocio.
"""

#: SVG mínimo pero válido (el plugin lo sirve tal cual).
_SVG = b'<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"></svg>'


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True)


def _commit(repo: Path, message: str) -> None:
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", message)


def _tag(repo: Path, version: str) -> None:
    _git(repo, "tag", f"book/{BOOK_ID}/v{version}")


def _write_chapters(repo: Path, mvc_md: str) -> None:
    book = repo / "books" / BOOK_ID
    (book / "assets").mkdir(parents=True, exist_ok=True)
    (book / "book.yml").write_text(_BOOK_YML, encoding="utf-8")
    (book / "01-introduccion.md").write_text(_INTRO_MD, encoding="utf-8")
    (book / "02-mvc.md").write_text(mvc_md, encoding="utf-8")
    (book / "03-model.md").write_text(_MODEL_MD, encoding="utf-8")
    (book / "assets" / "diagrama.svg").write_bytes(_SVG)


@pytest.fixture()
def repo(tmp_path: Path) -> Iterator[Path]:
    """Repo de contenidos propio del test: 3 capítulos + asset + enlace interno."""
    root = tmp_path / "dwes-content"
    root.mkdir()
    (root / "course.yml").write_text(_COURSE_YML, encoding="utf-8")
    (root / "README.md").write_text("# dwes-content\n", encoding="utf-8")
    _write_chapters(root, _MVC_MD_V1)
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.email", "e2e@example.com")
    _git(root, "config", "user.name", "E2E")
    _commit(root, "base: book con 3 capitulos")
    _tag(root, "1.0.0")
    yield root


@pytest.fixture()
def moodle() -> Iterator[MoodleRestClient]:
    """Cliente REST real contra moodle-docker; se cierra al terminar el test."""
    client = MoodleRestClient(os.environ["MOODLE_URL"], os.environ["MOODLE_TOKEN"])
    yield client
    http = getattr(client, "_client", None)
    if isinstance(http, httpx.Client):
        http.close()


def _service(
    root: Path, moodle: MoodleRestClient, store: ReleaseStore | None = None
) -> DeploymentService:
    releases = SqlReleasePort(store, source=SOURCE) if store is not None else NullReleasePort()
    return DeploymentService(LocalGitProvider(root), moodle, releases, source=SOURCE)


def _remote_chapter_html(moodle: MoodleRestClient, bookid: int, chapter_id: str) -> str:
    remote = moodle.get_book(bookid)
    assert remote is not None
    chapter = remote.chapters[chapter_id]
    return chapter.html


def test_ciclo_importacion(repo: Path, moodle: MoodleRestClient) -> None:
    """§32.5-6: importar desde cero crea el Book con imágenes y enlaces funcionando."""
    result = _service(repo, moodle).deploy(
        COURSE_ID, BOOK_ID, version="1.0.0", assume_yes=True, deployed_by="e2e"
    )
    assert result.success

    # La tabla del plugin registra source, content_id, version y git_commit (§32.6).
    record = moodle.get_deploy(COURSE_ID, SOURCE, BOOK_ID)
    assert record is not None
    assert record.source == SOURCE
    assert record.content_id == BOOK_ID
    assert record.content_version == "1.0.0"
    assert record.git_commit == LocalGitProvider(repo).get_commit(f"book/{BOOK_ID}/v1.0.0")

    # Imagen visible: la referencia assets/... quedó reescrita a pluginfile.php (§15).
    intro = _remote_chapter_html(moodle, record.bookid, "introduccion")
    assert "pluginfile.php" in intro
    assert "diagrama.svg" in intro

    # Enlace interno resuelto al capítulo Moodle, sin apuntar al .md (§16).
    remote = moodle.get_book(record.bookid)
    assert remote is not None
    assert "03-model.md" not in intro
    assert remote.chapters["model"].url in intro


def test_ciclo_actualizacion(repo: Path, moodle: MoodleRestClient) -> None:
    """§32.7-10: modificar + tag v1.1.0 → UPDATE_AVAILABLE y el mismo Book se actualiza."""
    service = _service(repo, moodle)
    service.deploy(COURSE_ID, BOOK_ID, version="1.0.0", assume_yes=True, deployed_by="e2e")
    bookid_v1 = moodle.get_deploy(COURSE_ID, SOURCE, BOOK_ID)
    assert bookid_v1 is not None

    # v1.1.0: se modifica 02-mvc.md y se etiqueta (§32.7-8).
    (repo / "books" / BOOK_ID / "02-mvc.md").write_text(_MVC_MD_V2, encoding="utf-8")
    _commit(repo, "update mvc")
    _tag(repo, "1.1.0")

    # El estado previo era UPDATE_AVAILABLE: hay versión nueva respecto a la desplegada.
    rows = service.course_status(COURSE_ID)
    assert len(rows) == 1
    assert rows[0].state.state is DeploymentState.UPDATE_AVAILABLE
    assert rows[0].state.version is not None
    assert str(rows[0].state.version) == "1.0.0"

    # §32.9: el plan de cambios se puede consultar antes de publicar.
    plan = service.plan(COURSE_ID, BOOK_ID, version="1.1.0")
    assert plan.actions

    # §32.10: el MISMO Book se actualiza (sin duplicados).
    result = service.deploy(COURSE_ID, BOOK_ID, version="1.1.0", assume_yes=True, deployed_by="e2e")
    assert result.success
    record = moodle.get_deploy(COURSE_ID, SOURCE, BOOK_ID)
    assert record is not None
    assert record.bookid == bookid_v1.bookid
    assert record.content_version == "1.1.0"
    remote = moodle.get_book(record.bookid)
    assert remote is not None
    assert len(remote.chapters) == len(CHAPTERS)
    mvc_html = remote.chapters["mvc"].html
    assert "Contenido de la versión 1.1.0" in mvc_html
    assert "Contenido de la versión 1.0.0" not in mvc_html


def test_ciclo_rollback(repo: Path, moodle: MoodleRestClient) -> None:
    """§32.11: desplegar de nuevo v1.0.0 devuelve el Book exactamente a ese estado."""
    service = _service(repo, moodle)
    service.deploy(COURSE_ID, BOOK_ID, version="1.0.0", assume_yes=True, deployed_by="e2e")
    (repo / "books" / BOOK_ID / "02-mvc.md").write_text(_MVC_MD_V2, encoding="utf-8")
    _commit(repo, "update mvc")
    _tag(repo, "1.1.0")
    service.deploy(COURSE_ID, BOOK_ID, version="1.1.0", assume_yes=True, deployed_by="e2e")
    bookid_v2 = moodle.get_deploy(COURSE_ID, SOURCE, BOOK_ID)
    assert bookid_v2 is not None
    assert bookid_v2.content_version == "1.1.0"

    # Rollback = redeploy idempotente de la versión conocida (§18).
    result = service.deploy(COURSE_ID, BOOK_ID, version="1.0.0", assume_yes=True, deployed_by="e2e")
    assert result.success
    record = moodle.get_deploy(COURSE_ID, SOURCE, BOOK_ID)
    assert record is not None
    assert record.bookid == bookid_v2.bookid  # mismo Book, no uno nuevo
    assert record.content_version == "1.0.0"
    remote = moodle.get_book(record.bookid)
    assert remote is not None
    mvc_html = remote.chapters["mvc"].html
    assert "Contenido de la versión 1.0.0" in mvc_html
    assert "Contenido de la versión 1.1.0" not in mvc_html


def test_ciclo_hotfix(repo: Path, moodle: MoodleRestClient, tmp_path: Path) -> None:
    """§32.13: versión critical/recalled → aviso a afectados y bloqueo de redeploys."""
    store = ReleaseStore(f"sqlite:///{tmp_path / 'e2e-releases.db'}")
    service = _service(repo, moodle, store)

    # v1.1.0 desplegada en el curso y v1.1.1 (el fix) ya taggeada: §11.1, forward-fix.
    service.deploy(COURSE_ID, BOOK_ID, version="1.0.0", assume_yes=True, deployed_by="e2e")
    (repo / "books" / BOOK_ID / "02-mvc.md").write_text(_MVC_MD_V2, encoding="utf-8")
    _commit(repo, "update mvc")
    _tag(repo, "1.1.0")
    (repo / "books" / BOOK_ID / "03-model.md").write_text(
        _MODEL_MD + "\nCorrección del hotfix.\n", encoding="utf-8"
    )
    _commit(repo, "fix: corrección urgente")
    _tag(repo, "1.1.1")
    service.deploy(COURSE_ID, BOOK_ID, version="1.1.0", assume_yes=True, deployed_by="e2e")

    # El coordinador marca v1.1.0 como crítica con recall (flujo §11.1).
    store.mark(
        f"book/{BOOK_ID}/v1.1.0",
        source=SOURCE,
        severity=Severity.CRITICAL,
        recalled=True,
        fixed_in="1.1.1",
        reason="El ejemplo del patrón Active Record contenía SQL inseguro",
        marked_by="coordinator",
    )

    # Cursos afectados: la consulta inversa sabe exactamente dónde está v1.1.0.
    assert service.where(SOURCE, BOOK_ID, "1.1.0") == [COURSE_ID]

    # El curso afectado ve UPDATE_AVAILABLE con el badge crítico.
    rows = service.course_status(COURSE_ID)
    assert len(rows) == 1
    assert rows[0].state.state is DeploymentState.UPDATE_AVAILABLE
    assert rows[0].state.severity is Severity.CRITICAL

    # Nuevos despliegues de la versión retirada quedan bloqueados (salvo --force).
    with pytest.raises(RecalledVersionError, match="RECALLED"):
        service.deploy(COURSE_ID, BOOK_ID, version="1.1.0", assume_yes=True)

    # El profesor actualiza al fix: el mismo pipeline, a v1.1.1.
    fixed = service.deploy(COURSE_ID, BOOK_ID, version="1.1.1", assume_yes=True, deployed_by="e2e")
    assert fixed.success
    record = moodle.get_deploy(COURSE_ID, SOURCE, BOOK_ID)
    assert record is not None
    assert record.content_version == "1.1.1"
    assert "Corrección del hotfix" in _remote_chapter_html(moodle, record.bookid, "model")
