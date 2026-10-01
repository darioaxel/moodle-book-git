"""Tests de los modelos de dominio (ENG-004)."""

from __future__ import annotations

import pytest

from courseascode.domain import (
    ActionKind,
    ContentId,
    DeploymentAction,
    DeploymentPlan,
    DeploymentResult,
    DeploymentState,
    GitRef,
    RefKind,
    SemVer,
    Severity,
)
from courseascode.domain.semver import SemVerError


class TestSemVer:
    def test_parse_basico(self) -> None:
        v = SemVer.parse("1.2.3")
        assert (v.major, v.minor, v.patch) == (1, 2, 3)
        assert v.prerelease is None
        assert v.build is None

    def test_parse_con_build_metadata(self) -> None:
        v = SemVer.parse("1.2.0+juan.3")
        assert v.build == "juan.3"
        assert str(v) == "1.2.0+juan.3"

    def test_build_metadata_no_afecta_a_la_igualdad(self) -> None:
        assert SemVer.parse("1.2.0+juan.3") == SemVer.parse("1.2.0")
        assert hash(SemVer.parse("1.2.0+juan.3")) == hash(SemVer.parse("1.2.0"))

    def test_ordenacion(self) -> None:
        assert SemVer.parse("1.2.0") < SemVer.parse("1.10.0")
        assert SemVer.parse("1.2.0") < SemVer.parse("2.0.0")
        assert SemVer.parse("1.0.0-alpha") < SemVer.parse("1.0.0")

    def test_from_tag(self) -> None:
        v = SemVer.from_tag("book/ut03-mvc/v1.2.0")
        assert v == SemVer.parse("1.2.0")

    def test_from_tag_invalido(self) -> None:
        with pytest.raises(SemVerError):
            SemVer.from_tag("v1.2.0")
        with pytest.raises(SemVerError):
            SemVer.from_tag("book/ut03-mvc/1.2.0")

    def test_parse_invalido(self) -> None:
        for bad in ("", "1.2", "1.2.x", "01.2.3", "1.2.3-"):
            with pytest.raises(SemVerError):
                SemVer.parse(bad)


class TestContentId:
    def test_str(self) -> None:
        assert str(ContentId("dwes", "ut03-mvc")) == "@dwes/ut03-mvc"

    def test_parse(self) -> None:
        cid = ContentId.parse("@dwes/ut03-mvc")
        assert cid.source == "dwes"
        assert cid.id == "ut03-mvc"

    def test_parse_sin_arroba(self) -> None:
        assert ContentId.parse("juan/ut03-mvc") == ContentId("juan", "ut03-mvc")

    @pytest.mark.parametrize("bad", ["", "@dwes", "dwes/", "@/ut03", "a/b/c"])
    def test_parse_invalido(self, bad: str) -> None:
        with pytest.raises(ValueError):
            ContentId.parse(bad)


class TestGitRef:
    def test_tag(self) -> None:
        ref = GitRef.of("book/ut03-mvc/v1.0.0")
        assert ref.kind is RefKind.TAG

    def test_commit(self) -> None:
        assert GitRef.of("8f31a2c").kind is RefKind.COMMIT
        assert GitRef.of("a" * 40).kind is RefKind.COMMIT

    def test_rama(self) -> None:
        assert GitRef.of("main").kind is RefKind.BRANCH
        assert GitRef.of("juan").kind is RefKind.BRANCH


class TestDeploymentPlan:
    def _plan(self, actions: tuple[DeploymentAction, ...]) -> DeploymentPlan:
        return DeploymentPlan(
            course_id=42,
            content=ContentId("dwes", "ut03-mvc"),
            current_version=SemVer.parse("1.1.0"),
            target_version=SemVer.parse("1.2.0"),
            actions=actions,
        )

    def test_sin_eliminaciones_no_requiere_confirmacion(self) -> None:
        plan = self._plan(
            (
                DeploymentAction(kind=ActionKind.UPDATE, target="chapter", stable_id="mvc"),
                DeploymentAction(kind=ActionKind.CREATE, target="chapter", stable_id="controller"),
                DeploymentAction(kind=ActionKind.UPLOAD, target="asset", title="mvc.svg"),
            )
        )
        assert not plan.has_deletions
        assert not plan.requires_confirmation

    def test_eliminacion_requiere_confirmacion(self) -> None:
        plan = self._plan(
            (
                DeploymentAction(
                    kind=ActionKind.DELETE,
                    target="chapter",
                    stable_id="observer",
                    requires_confirmation=True,
                ),
            )
        )
        assert plan.has_deletions
        assert plan.requires_confirmation

    def test_summary_contiene_versiones(self) -> None:
        plan = self._plan(())
        summary = plan.summary()
        assert "1.1.0" in summary
        assert "@dwes/ut03-mvc" in summary


class TestDeploymentResult:
    def test_resultado_ok(self) -> None:
        result = DeploymentResult(success=True, message="deployed", duration_seconds=1.5)
        assert result.success


class TestEstados:
    def test_todos_los_estados_existen(self) -> None:
        assert {s.value for s in DeploymentState} == {
            "NOT_DEPLOYED",
            "UP_TO_DATE",
            "UPDATE_AVAILABLE",
            "DRIFT_DETECTED",
            "DEPLOYING",
            "ERROR",
        }

    def test_severidad(self) -> None:
        assert Severity.CRITICAL.value == "critical"
        assert Severity.NORMAL.value == "normal"
