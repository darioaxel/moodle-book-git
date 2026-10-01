"""Tests de la configuración por entorno (ENG-005)."""

from __future__ import annotations

import pytest

from courseascode.settings import SettingsError, load_settings


def test_load_settings_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MOODLE_URL", "https://moodle.example.com")
    monkeypatch.setenv("MOODLE_TOKEN", "token123")
    monkeypatch.setenv("CONTENT_REPO_URL", "git@github.com:example/dwes-content.git")
    monkeypatch.setenv("CONTENT_REPO_KEY", "ssh-key")
    settings = load_settings()
    assert str(settings.moodle_url) == "https://moodle.example.com/"
    assert settings.moodle_token == "token123"


def test_load_settings_falla_ruidosamente_si_falta_algo(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for var in ("MOODLE_URL", "MOODLE_TOKEN", "CONTENT_REPO_URL", "CONTENT_REPO_KEY"):
        monkeypatch.delenv(var, raising=False)
    with pytest.raises(SettingsError, match="MOODLE_URL"):
        load_settings()


def test_moodle_rest_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MOODLE_URL", "https://moodle.example.com/")
    monkeypatch.setenv("MOODLE_TOKEN", "t")
    monkeypatch.setenv("CONTENT_REPO_URL", "u")
    monkeypatch.setenv("CONTENT_REPO_KEY", "k")
    settings = load_settings()
    assert settings.moodle_rest_url == "https://moodle.example.com/webservice/rest/server.php"
