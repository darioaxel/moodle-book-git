"""Configuración por entorno del servicio (§25 de la spec).

Las credenciales **nunca** viven en el repositorio: solo variables de entorno.
Si falta alguna obligatoria, el fallo es ruidoso en el arranque.
"""

from __future__ import annotations

from pydantic import AliasChoices, AnyHttpUrl, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class SettingsError(RuntimeError):
    """Configuración incompleta o inválida."""


class Settings(BaseSettings):
    """Variables de entorno del engine.

    Las cuatro primeras son el mínimo del servicio (§25, fallo ruidoso al
    arrancar). Las tres últimas son **opcionales** y tienen defaults seguros:
    sin BD el servicio funciona con ``NullReleasePort`` (sin severidades ni
    recall), sin token de coordinador el comando ``release mark`` y el
    endpoint de auditoría quedan deshabilitados, y sin secreto el webhook
    ``POST /hooks/git`` responde 503.
    """

    model_config = SettingsConfigDict(extra="ignore")

    moodle_url: AnyHttpUrl = Field(description="URL base de Moodle")
    moodle_token: str = Field(min_length=1, description="Token de la cuenta técnica")
    content_repo_url: str = Field(min_length=1, description="URL del repo de contenidos")
    content_repo_key: str = Field(min_length=1, description="Deploy key de solo lectura")

    db_url: str = Field(
        default="sqlite:///~/.courseascode/courseascode.db",
        validation_alias=AliasChoices("COURSEASCODE_DB", "DB_URL"),
        description="URL SQLAlchemy de la BD de releases/auditoría (ENG-090)",
    )
    admin_token: str | None = Field(
        default=None,
        validation_alias=AliasChoices("COURSEASCODE_ADMIN_TOKEN", "ADMIN_TOKEN"),
        description="Token del rol coordinador: `release mark` y auditoría (ENG-091)",
    )
    webhook_secret: str | None = Field(
        default=None,
        validation_alias=AliasChoices("COURSEASCODE_WEBHOOK_SECRET", "WEBHOOK_SECRET"),
        description="Secreto HMAC del webhook de Git (ENG-093); sin él el endpoint va 503",
    )

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
