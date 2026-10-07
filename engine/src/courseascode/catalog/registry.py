"""Registro de fuentes con visibilidad y ACL (ENG-052, §12.2).

Cada fuente es un namespace de Books (p. ej. ``dwes``) con un propietario y una
visibilidad: ``equipo`` la ve cualquier llamante; ``privada`` solo su
propietario. En la Beta hay una única fuente oficial de equipo, pero la
estructura y la ACL quedan implementadas y testeadas.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

SourceVisibility = Literal["equipo", "privada"]


class Source(BaseModel):
    """Fuente de contenidos: namespace + propietario + visibilidad."""

    model_config = ConfigDict(frozen=True)

    name: str = Field(min_length=1, description="Namespace, p. ej. dwes")
    owner: str = Field(min_length=1, description="Identidad propietaria (visibilidad privada)")
    visibility: SourceVisibility = "equipo"


class SourceRegistry:
    """Fuentes conocidas del servicio y su regla de visibilidad."""

    def __init__(self, sources: list[Source] | tuple[Source, ...]) -> None:
        self._sources = tuple(sources)

    @property
    def sources(self) -> tuple[Source, ...]:
        return self._sources

    def get(self, name: str) -> Source | None:
        """Fuente por nombre, o ``None`` si no está registrada."""
        return next((s for s in self._sources if s.name == name), None)

    def list_visible(self, caller: str) -> list[Source]:
        """Fuentes que ``caller`` puede ver: las de equipo y las que posee."""
        return [s for s in self._sources if s.visibility == "equipo" or s.owner == caller]

    def is_visible(self, source: str, caller: str) -> bool:
        """``True`` si ``caller`` puede ver la fuente ``source``."""
        found = self.get(source)
        return found is not None and (found.visibility == "equipo" or found.owner == caller)

    @classmethod
    def default(cls) -> SourceRegistry:
        """Registro de la Beta: la fuente oficial única de equipo.

        El nombre del namespace es configuración de presentación, no de Git
        (§8.1); se fija aquí y en fases posteriores podrá venir de ``Settings``.
        """
        return cls([Source(name="dwes", owner="coordinacion", visibility="equipo")])
