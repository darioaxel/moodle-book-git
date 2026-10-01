"""SemVer con soporte de build metadata (p. ej. ``1.2.0+juan.3``).

La precedencia ignora la build metadata, según la especificación SemVer:
``1.2.0+juan.3 == 1.2.0``. La versión de una rama personal se calcula como
``tag oficial base + commits ahead`` (§8.2 de la spec), p. ej. ``1.2.0+juan.3``.
"""

from __future__ import annotations

import re
from functools import total_ordering
from typing import Any

from pydantic_core import core_schema

_SEMVER_RE = re.compile(
    r"^(?P<major>0|[1-9]\d*)\.(?P<minor>0|[1-9]\d*)\.(?P<patch>0|[1-9]\d*)"
    r"(?:-(?P<prerelease>[0-9A-Za-z.-]+))?"
    r"(?:\+(?P<build>[0-9A-Za-z.-]+))?$"
)

_TAG_PREFIX_RE = re.compile(r"^book/(?P<book_id>[^/]+)/v(?P<version>\S+)$")


class SemVerError(ValueError):
    """Cadena que no es una versión semántica válida."""


@total_ordering
class SemVer:
    """Versión semántica inmutable."""

    __slots__ = ("build", "major", "minor", "patch", "prerelease")

    def __init__(
        self,
        major: int,
        minor: int,
        patch: int,
        prerelease: str | None = None,
        build: str | None = None,
    ) -> None:
        for value, name in ((major, "major"), (minor, "minor"), (patch, "patch")):
            if value < 0:
                msg = f"{name} no puede ser negativo: {value}"
                raise SemVerError(msg)
        self.major = major
        self.minor = minor
        self.patch = patch
        self.prerelease = prerelease
        self.build = build

    @classmethod
    def parse(cls, text: str) -> SemVer:
        match = _SEMVER_RE.match(text.strip())
        if match is None:
            msg = f"Versión SemVer inválida: {text!r}"
            raise SemVerError(msg)
        return cls(
            major=int(match["major"]),
            minor=int(match["minor"]),
            patch=int(match["patch"]),
            prerelease=match["prerelease"],
            build=match["build"],
        )

    @classmethod
    def from_tag(cls, tag: str) -> SemVer:
        """Extrae la versión de un tag ``book/<id>/vX.Y.Z``."""
        match = _TAG_PREFIX_RE.match(tag.strip())
        if match is None:
            msg = f"Tag de Book inválido (se esperaba 'book/<id>/vX.Y.Z'): {tag!r}"
            raise SemVerError(msg)
        return cls.parse(match["version"])

    def precedence_key(self) -> tuple[int, int, int, tuple[tuple[int, str], ...]]:
        """Clave de ordenación sin build metadata (SemVer §11)."""
        prerelease_key: tuple[tuple[int, str], ...] = ()
        if self.prerelease is not None:
            prerelease_key = tuple(
                (0, ident) if ident.isdigit() else (1, ident)
                for ident in self.prerelease.split(".")
            )
        # Sin prerelease ordena después que con prerelease: se codifica con un
        # identificador que gana a cualquier prerelease real.
        return (self.major, self.minor, self.patch, prerelease_key or ((2, ""),))

    def __str__(self) -> str:
        text = f"{self.major}.{self.minor}.{self.patch}"
        if self.prerelease is not None:
            text += f"-{self.prerelease}"
        if self.build is not None:
            text += f"+{self.build}"
        return text

    def __repr__(self) -> str:
        return f"SemVer({str(self)!r})"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, SemVer):
            return NotImplemented
        return self.precedence_key() == other.precedence_key()

    def __lt__(self, other: SemVer) -> bool:
        if not isinstance(other, SemVer):
            return NotImplemented
        return self.precedence_key() < other.precedence_key()

    def __hash__(self) -> int:
        return hash(self.precedence_key())

    @classmethod
    def _validate(cls, value: Any) -> SemVer:
        if isinstance(value, cls):
            return value
        if isinstance(value, str):
            return cls.parse(value)
        msg = f"SemVer esperaba str o SemVer, recibió {type(value).__name__}"
        raise TypeError(msg)

    @classmethod
    def __get_pydantic_core_schema__(
        cls, _source_type: Any, _handler: Any
    ) -> core_schema.CoreSchema:
        return core_schema.json_or_python_schema(
            python_schema=core_schema.no_info_plain_validator_function(cls._validate),
            json_schema=core_schema.no_info_after_validator_function(
                cls._validate, core_schema.str_schema()
            ),
            serialization=core_schema.plain_serializer_function_ser_schema(str, when_used="json"),
        )
