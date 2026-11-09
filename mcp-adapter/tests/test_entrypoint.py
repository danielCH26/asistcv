"""Regresión del entrypoint del adapter MCP (issue #132).

El bug: `getattr(structlog, level, structlog.INFO)` — el tercer argumento de
`getattr` es su valor por defecto y se evalúa SIEMPRE, antes de la llamada.
structlog no expone constantes de nivel a nivel de módulo, así que el import
de `asistcv_mcp.__main__` reventaba con AttributeError y el servidor MCP no
arrancaba para nadie (la config de Claude Desktop del README no fija LOG_LEVEL,
así que usaba el default "INFO").

Los tests de tools no lo detectaban porque nunca importaban el entrypoint:
el bug pasaba el gate de CI y sólo aparecía al levantar el bot de verdad.
"""

import importlib
import io
import logging
import sys
from collections.abc import Callable, Iterator
from types import ModuleType

import pytest
import structlog

from asistcv_mcp.config import get_settings


@pytest.fixture
def load_entrypoint(
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[Callable[[dict[str, str]], tuple[ModuleType, io.StringIO]]]:
    """Reimporta `__main__` con settings re-leídos y con el env que se le pase.

    - Se saca el módulo de `sys.modules` para forzar la re-ejecución del
      código a nivel de módulo (que es donde vivía el crash).
    - `sys.stderr` se sustituye por un buffer propio: el entrypoint enlaza
      `WriteLoggerFactory(file=sys.stderr)` al importar, y pytest reemplaza
      y cierra ese stream al final de cada test. Sin este aislamiento, el
      logger global queda apuntando a un file cerrado y revienta con
      "I/O operation on closed file" en el resto de la suite.
    - Al final se restaura la config global de structlog.
    """

    def _load(env: dict[str, str]) -> tuple[ModuleType, io.StringIO]:
        for key, value in env.items():
            monkeypatch.setenv(key, value)
        buffer = io.StringIO()
        monkeypatch.setattr(sys, "stderr", buffer)
        get_settings.cache_clear()
        sys.modules.pop("asistcv_mcp.__main__", None)
        module = importlib.import_module("asistcv_mcp.__main__")
        return module, buffer

    yield _load

    # Dejar el estado global como estaba para el resto de la suite.
    get_settings.cache_clear()
    sys.modules.pop("asistcv_mcp.__main__", None)
    structlog.reset_defaults()


def test_entrypoint_imports_without_attribute_error(
    load_entrypoint: Callable[[dict[str, str]], tuple[ModuleType, io.StringIO]],
) -> None:
    """El import del entrypoint no debe reventar con ningún LOG_LEVEL."""
    module, _ = load_entrypoint({})
    assert module.logger is not None


def test_entrypoint_imports_with_debug_level(
    load_entrypoint: Callable[[dict[str, str]], tuple[ModuleType, io.StringIO]],
) -> None:
    module, _ = load_entrypoint({"LOG_LEVEL": "DEBUG"})
    assert module.logger is not None


def test_unknown_log_level_falls_back_to_info(
    load_entrypoint: Callable[[dict[str, str]], tuple[ModuleType, io.StringIO]],
) -> None:
    """Un nivel inventado no debe tumbar el arranque."""
    module, _ = load_entrypoint({"LOG_LEVEL": "NO_EXISTE"})
    assert module.logger is not None


def test_debug_events_reach_stderr_when_level_is_debug(
    load_entrypoint: Callable[[dict[str, str]], tuple[ModuleType, io.StringIO]],
) -> None:
    """Con LOG_LEVEL=DEBUG el evento se escribe en stderr (nunca en stdout).

    stderr es el canal seguro: stdout es el stdio del protocolo MCP.
    """
    module, buffer = load_entrypoint({"LOG_LEVEL": "DEBUG"})
    module.logger.debug("probe_debug_event")
    assert "probe_debug_event" in buffer.getvalue()


def test_debug_events_are_filtered_when_level_is_info(
    load_entrypoint: Callable[[dict[str, str]], tuple[ModuleType, io.StringIO]],
) -> None:
    """Con el default INFO, un evento debug no debe emitirse."""
    module, buffer = load_entrypoint({"LOG_LEVEL": "INFO"})
    module.logger.debug("probe_debug_event")
    assert "probe_debug_event" not in buffer.getvalue()


def test_log_level_is_mapped_to_the_standard_logging_ints() -> None:
    """El nivel de settings mapea al int que espera make_filtering_bound_logger."""
    mapping = logging.getLevelNamesMapping()
    assert mapping["DEBUG"] == logging.DEBUG
    assert mapping["INFO"] == logging.INFO
    assert mapping["WARNING"] == logging.WARNING
    assert mapping["ERROR"] == logging.ERROR
