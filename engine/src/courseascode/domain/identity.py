"""Identidad del contenido: ``(source, id, version)`` (§7 de la spec)."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic_core import core_schema

_CONTENT_ID_PARTS = 2  # source + id


class RefKind(Enum):
    """Tipo de referencia Git resuelta."""

    TAG = "tag"
    BRANCH = "branch"
    COMMIT = "commit"


class GitRef:
    """Referencia Git inmutable: tag, rama o commit (§17 paso 1)."""

    __slots__ = ("kind", "value")

    def __init__(self, value: str, kind: RefKind) -> None:
        self.value = value
        self.kind = kind

    @classmethod
    def of(cls, value: str) -> GitRef:
        """Infere el tipo a partir de la forma de la referencia."""
        if value.startswith("book/") and "/v" in value:
            return cls(value, RefKind.TAG)
        if len(value) in (7, 40) and all(c in "0123456789abcdef" for c in value):
            return cls(value, RefKind.COMMIT)
        return cls(value, RefKind.BRANCH)

    def __str__(self) -> str:
        return self.value

    def __repr__(self) -> str:
        return f"GitRef({self.value!r}, {self.kind.value!r})"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, GitRef):
            return NotImplemented
        return (self.value, self.kind) == (other.value, other.kind)

    def __hash__(self) -> int:
        return hash((self.value, self.kind))


class ContentId:
    """Identidad de un contenido: namespace ``source`` + ``id`` estable.

    Se muestra como ``@dwes/ut03-mvc`` (oficial) o ``@juan/ut03-mvc`` (personal).
    """

    __slots__ = ("id", "source")

    def __init__(self, source: str, id: str) -> None:
        if not source or not id:
            msg = "ContentId requiere source e id no vacíos"
            raise ValueError(msg)
        self.source = source
        self.id = id

    @classmethod
    def parse(cls, text: str) -> ContentId:
        """Parsea ``@dwes/ut03-mvc`` o ``dwes/ut03-mvc``."""
        normalized = text.strip().lstrip("@")
        parts = normalized.split("/")
        if len(parts) != _CONTENT_ID_PARTS or not all(parts):
            msg = f"ContentId inválido (se esperaba '@source/id'): {text!r}"
            raise ValueError(msg)
        return cls(source=parts[0], id=parts[1])

    def __str__(self) -> str:
        return f"@{self.source}/{self.id}"

    def __repr__(self) -> str:
        return f"ContentId({str(self)!r})"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, ContentId):
            return NotImplemented
        return (self.source, self.id) == (other.source, other.id)

    def __hash__(self) -> int:
        return hash((self.source, self.id))

    @classmethod
    def _validate(cls, value: Any) -> ContentId:
        if isinstance(value, cls):
            return value
        if isinstance(value, str):
            return cls.parse(value)
        msg = f"ContentId esperaba str o ContentId, recibió {type(value).__name__}"
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
