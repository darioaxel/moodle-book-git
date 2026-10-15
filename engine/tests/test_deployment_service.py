"""Tests del ``DeploymentService``: resolución de refs, validación y pipeline."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from courseascode.deployment import DeploymentService, DeploymentServiceError
from courseascode.domain.semver import SemVer
from courseascode.git import LocalGitProvider
from courseascode.moodle import FakeMoodleProvider, MoodleError

COURSE = 2026
SOURCE = "dwes"
BOOK = "ut03-mvc"


@pytest.fixture()
def service(git_repo: Path) -> tuple[DeploymentService, FakeMoodleProvider]:
    fake = FakeMoodleProvider(course_ids=(COURSE,))
    return DeploymentService(LocalGitProvider(git_repo), fake, source=SOURCE), fake


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True)


def test_plan_con_version_resuelve_el_tag(
    service: tuple[DeploymentService, FakeMoodleProvider],
) -> None:
    deployment, _fake = service
    plan = deployment.plan(COURSE, BOOK, version="1.1.0")
    assert plan.target_version == SemVer.parse("1.1.0")
    assert plan.git_ref == f"book/{BOOK}/v1.1.0"
    SHA_LENGTH = 40
    assert len(plan.git_commit) == SHA_LENGTH
    # Sección Changes (§17.1): primer deploy, todo es nuevo.
    assert any(change.startswith("+ 01-introduccion.md") for change in plan.changes)
    deployment.deploy(COURSE, BOOK, version="1.0.0", assume_yes=True)
    plan = deployment.plan(COURSE, BOOK, version="1.1.0")
    assert any(change.startswith("+ 06-observer.md") for change in plan.changes)
    assert any(change.startswith("~ 02-mvc.md") for change in plan.changes)


def test_plan_con_ref_de_rama_deriva_version(
    service: tuple[DeploymentService, FakeMoodleProvider],
) -> None:
    deployment, _fake = service
    plan = deployment.plan(COURSE, BOOK, ref="juan")
    assert plan.target_version == SemVer.parse("1.2.0+juan.3")
    assert plan.git_ref == "juan"


def test_plan_sin_version_ni_ref_usa_la_ultima(
    service: tuple[DeploymentService, FakeMoodleProvider],
) -> None:
    deployment, _fake = service
    plan = deployment.plan(COURSE, BOOK)
    assert plan.target_version == SemVer.parse("1.2.0")


def test_version_y_ref_a_la_vez_rechazado(
    service: tuple[DeploymentService, FakeMoodleProvider],
) -> None:
    deployment, _fake = service
    with pytest.raises(DeploymentServiceError, match="no ambos"):
        deployment.plan(COURSE, BOOK, version="1.0.0", ref="main")


def test_version_invalida_rechazada(
    service: tuple[DeploymentService, FakeMoodleProvider],
) -> None:
    deployment, _fake = service
    with pytest.raises(DeploymentServiceError, match="SemVer"):
        deployment.plan(COURSE, BOOK, version="v1.0")


def test_book_desconocido_rechazado(
    service: tuple[DeploymentService, FakeMoodleProvider],
) -> None:
    deployment, _fake = service
    with pytest.raises(DeploymentServiceError, match=r"course\.yml"):
        deployment.plan(COURSE, "ut99", ref="main")  # ref válido, book ausente


def test_validacion_fallida_bloquea_el_deploy(
    service: tuple[DeploymentService, FakeMoodleProvider], git_repo: Path
) -> None:
    """Un repo inválido no se puede publicar (§17 pasos 3-4, §20)."""
    deployment, fake = service
    model = git_repo / "books" / BOOK / "03-model.md"
    model.write_text(
        model.read_text(encoding="utf-8") + "\n:::note\nContenedor sin cerrar\n", "utf-8"
    )
    _git(git_repo, "add", "-A")
    _git(git_repo, "commit", "-qm", "contenido roto")
    _git(git_repo, "tag", f"book/{BOOK}/v1.3.0")

    with pytest.raises(DeploymentServiceError, match="validación fallida"):
        deployment.plan(COURSE, BOOK, version="1.3.0")

    assert fake.get_deploy(COURSE, SOURCE, BOOK) is None  # no se tocó nada


def test_curso_inexistente_en_moodle_falla(
    service: tuple[DeploymentService, FakeMoodleProvider],
) -> None:
    deployment, _fake = service
    with pytest.raises(MoodleError, match="invalid_course"):
        deployment.plan(999_999, BOOK, version="1.0.0")


def test_deploy_registra_procedencia_git(
    service: tuple[DeploymentService, FakeMoodleProvider], git_repo: Path
) -> None:
    deployment, fake = service
    deployment.deploy(COURSE, BOOK, version="1.0.0", assume_yes=True, deployed_by="tester")
    record = fake.get_deploy(COURSE, SOURCE, BOOK)
    assert record is not None
    assert record.deployed_by == "tester"
    assert record.git_ref == f"book/{BOOK}/v1.0.0"
    assert record.status == "success"
    # El commit registrado es el SHA real del tag (peela la tag).
    assert (
        record.git_commit
        == subprocess.run(
            ["git", "-C", str(git_repo), "rev-parse", f"book/{BOOK}/v1.0.0^{{}}"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    )
