"""Configuración por entorno del servicio (§25 de la spec).

Las credenciales **nunca** viven en el repositorio: solo variables de entorno.
Si falta alguna obligatoria, el fallo es ruidoso en el arranque.
"""

from __future__ import annotations

from pydantic import AnyHttpUrl, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class SettingsError(RuntimeError):
    """Configuración incompleta o inválida."""


class Settings(BaseSettings):
    """Variables de entorno del engine (todas obligatorias)."""

    model_config = SettingsConfigDict(extra="ignore")

    moodle_url: AnyHttpUrl = Field(description="URL base de Moodle")
    moodle_token: str = Field(min_length=1, description="Token de la cuenta técnica")
    content_repo_url: str = Field(min_length=1, description="URL del repo de contenidos")
    content_repo_key: str = Field(min_length=1, description="Deploy key de solo lectura")

    @property
    def moodle_rest_url(self) -> str:
        return f"{str(self.moodle_url).rstrip('/')}/webservice/rest/server.php"


def load_settings() -> Settings:
    """Carga la configuración; falla ruidosamente si falta algo."""
    try:
        return Settings()  # type: ignore[call-arg]
    except Exception as exc:
        msg = (
            "Configuración incompleta. Define las variables de entorno: "
            "MOODLE_URL, MOODLE_TOKEN, CONTENT_REPO_URL, CONTENT_REPO_KEY. "
            f"Detalle: {exc}"
        )
        raise SettingsError(msg) from exc
