"""Cache TTL en proceso, con capacidad acotada y expulsión por antigüedad.

Uso local del adapter (issue #59): cache de resultados de ``web_search`` por
query exacta, TTL 1h, máximo de entradas fijo. No hay evicción LRU por acceso
— la antigüedad es de inserción — porque la simpleza gana para un cache
personal de una sola máquina.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Final

_DEFAULT_MAX_ENTRIES: Final[int] = 128


class TTLCache:
    """Cache en memoria con expiración por TTL y tope de entradas.

    ``now_fn`` es inyectable para tests (por defecto ``time.monotonic``, que
    no se ve afectado por cambios de reloj de pared).
    """

    def __init__(
        self,
        ttl_seconds: float,
        max_entries: int = _DEFAULT_MAX_ENTRIES,
        now_fn: Callable[[], float] = time.monotonic,
    ) -> None:
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds debe ser positivo")
        if max_entries < 1:
            raise ValueError("max_entries debe ser >= 1")
        self._ttl = ttl_seconds
        self._max_entries = max_entries
        self._now_fn = now_fn
        # dict preserva orden de inserción: el primer ítem es el más viejo.
        self._data: dict[str, tuple[float, dict[str, object]]] = {}

    def get(self, key: str) -> dict[str, object] | None:
        """Devuelve el valor si existe y no expiró; None en miss o expiración."""
        entry = self._data.get(key)
        if entry is None:
            return None
        stored_at, value = entry
        if self._now_fn() - stored_at >= self._ttl:
            del self._data[key]
            return None
        return value

    def set(self, key: str, value: dict[str, object]) -> None:
        """Inserta o reemplaza; expulsa el más viejo si se supera el tope."""
        if key in self._data:
            del self._data[key]
        while len(self._data) >= self._max_entries:
            oldest = next(iter(self._data))
            del self._data[oldest]
        self._data[key] = (self._now_fn(), value)
