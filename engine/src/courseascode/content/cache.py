"""Caché de renders por commit (ENG-103).

Los **tags son inmutables** (§8.3): renderizar dos veces el mismo
``(commit_sha, book_id, kind)`` devuelve el mismo HTML, así que el resultado
se puede cachear de forma agresiva. La política de seguridad es sencilla:

- Solo entran refs que resuelven a **tag o commit sha**; las ramas (el ref
  puede moverse) y el *working tree* (cambia con cada edición) **nunca** se
  cachean. La decisión la toma el caller (``web/app.py``) al construir la
  clave; el caché no interpreta refs.
- Los renders de despliegue **no** se cachean: sus ``AssetRef.local_path``
  apuntan al worktree efímero del checkout, que se elimina al terminar el
  plan, y sus adapters incrustan URLs de Moodle propias del curso/Book. El
  caché cubre la preview web, donde el HTML cacheado solo se lee (los assets
  se sirven por ruta, no desde el ``RenderedBook``).
- Un webhook de Git invalida el caché completo (política conservadora, §10.4).

Implementación: memoria compartida + ``threading.Lock`` (la app web es
multihilo), TTL (defecto 15 min) y tamaño máximo (defecto 64 entradas) con
evicción de la entrada más antigua. El reloj es inyectable para tests. En
carrera, dos hilos pueden renderizar la misma clave a la vez: la última
escritura gana; se asume (correctamente para el renderer) que ambos valores
son idénticos.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Hashable
from dataclasses import dataclass

#: Clave del caché: (commit_sha, book_id, kind). ``kind`` distingue renders
#: hechos con adapters distintos (p. ej. "preview" vs futuros adapters).
CacheKey = tuple[Hashable, ...]

DEFAULT_TTL_SECONDS = 900.0  # 15 min
DEFAULT_MAX_ENTRIES = 64


@dataclass(frozen=True)
class _Entry[T]:
    value: T
    created: float


class RenderCache[T]:
    """Caché en memoria thread-safe de renders (o cualquier valor) por clave."""

    def __init__(
        self,
        ttl_seconds: float = DEFAULT_TTL_SECONDS,
        max_entries: int = DEFAULT_MAX_ENTRIES,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if ttl_seconds <= 0:
            msg = f"ttl_seconds debe ser positivo: {ttl_seconds}"
            raise ValueError(msg)
        if max_entries < 1:
            msg = f"max_entries debe ser >= 1: {max_entries}"
            raise ValueError(msg)
        self._ttl = ttl_seconds
        self._max = max_entries
        self._clock = clock
        self._entries: dict[CacheKey, _Entry[T]] = {}
        self._lock = threading.Lock()

    def get(self, key: CacheKey) -> T | None:
        """Valor de ``key`` si existe y no ha caducado; ``None`` en caso contrario."""
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return None
            if self._clock() - entry.created > self._ttl:
                del self._entries[key]
                return None
            return entry.value

    def set(self, key: CacheKey, value: T) -> None:
        """Guarda ``value`` bajo ``key``, evictando la entrada más antigua si lleno."""
        with self._lock:
            if key not in self._entries and len(self._entries) >= self._max:
                oldest = min(self._entries, key=lambda k: self._entries[k].created)
                del self._entries[oldest]
            self._entries[key] = _Entry(value=value, created=self._clock())

    def get_or_render(self, key: CacheKey, producer: Callable[[], T]) -> T:
        """Devuelve el valor cacheado o lo produce, guarda y devuelve."""
        cached = self.get(key)
        if cached is not None:
            return cached
        value = producer()
        self.set(key, value)
        return value

    def clear(self) -> None:
        """Vacía el caché (invalidación por webhook, ENG-093/ENG-103)."""
        with self._lock:
            self._entries.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._entries)
