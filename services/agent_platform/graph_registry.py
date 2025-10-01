"""
# NOTE: this is a ligher model and only stores the Pregel instance.
"""

from __future__ import annotations

import importlib
import importlib.util
import json
import logging
import os
import sys
from pathlib import Path
from types import ModuleType
from typing import Dict, Iterable

from langgraph.graph import StateGraph
from langgraph.pregel import Pregel

logger = logging.getLogger("graph_registry")

GraphInstance = Pregel

_GRAPHS: Dict[str, GraphInstance] = {}
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_CONFIG_PATH = _PROJECT_ROOT / "langgraph.json"


class GraphRegistryError(RuntimeError):
    """Raised when a graph cannot be loaded or is misconfigured."""


class GraphNotFoundError(KeyError):
    """Raised when a requested graph id is not present in the registry."""


def load_graphs_from_file(
    config_path: str | Path | None = None,
    *,
    force: bool = False,
) -> int:
    """Populate the in-memory registry from a ``langgraph.json`` file.

    Args:
            config_path: Optional override path to the JSON manifest.
            force: When ``True`` the registry is rebuilt even if already populated.

    Returns:
            The number of graphs currently registered.
    """

    path = _resolve_config_path(config_path)

    if _GRAPHS and not force:
        return len(_GRAPHS)

    if not path.exists():
        logger.warning("langgraph.json not found at %s; registry remains empty", path)
        _GRAPHS.clear()
        return 0

    try:
        config_doc = _load_config(path)
    except Exception as exc:  # pragma: no cover - logged and re-raised
        logger.exception("Failed to load graph configuration from %s", path)
        raise GraphRegistryError(str(exc)) from exc

    loaded: Dict[str, GraphInstance] = {}
    for graph_id, locator in config_doc.items():
        try:
            graph = _import_graph(locator, base_path=path.parent)
        except Exception as exc:  # pragma: no cover - logged and re-raised
            logger.exception(
                "Unable to register graph '%s' from '%s'", graph_id, locator
            )
            raise GraphRegistryError(
                f"Failed to load graph '{graph_id}' from '{locator}'"
            ) from exc
        loaded[graph_id] = graph

    _GRAPHS.clear()
    _GRAPHS.update(loaded)

    logger.info("Registered %d graph(s) from %s", len(_GRAPHS), path)
    return len(_GRAPHS)


def register_graph(graph_id: str, graph: GraphInstance) -> None:
    """Manually register a graph instance."""

    if not isinstance(graph, Pregel):
        raise GraphRegistryError(
            f"Graph '{graph_id}' must be a compiled Pregel instance; got {type(graph)!r}"
        )
    _GRAPHS[graph_id] = graph


def get_graph(graph_id: str) -> GraphInstance:
    """Return the registered graph for ``graph_id`` or raise."""

    try:
        return _GRAPHS[graph_id]
    except KeyError as exc:
        raise GraphNotFoundError(graph_id) from exc


def graph_exists(graph_id: str) -> bool:
    """Check whether a graph is available in the registry."""

    return graph_id in _GRAPHS


def list_graphs() -> Iterable[str]:
    """Iterate over registered graph identifiers."""

    return tuple(_GRAPHS.keys())


def clear_registry() -> None:
    """Remove all registered graphs. Primarily useful for testing."""

    _GRAPHS.clear()


def _resolve_config_path(config_path: str | Path | None) -> Path:
    if config_path is not None:
        return Path(config_path).expanduser().resolve()

    env_path = os.getenv("LANGGRAPH_SPEC_PATH")
    if env_path:
        return Path(env_path).expanduser().resolve()

    return _DEFAULT_CONFIG_PATH


def _load_config(path: Path) -> Dict[str, str]:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)

    if not isinstance(payload, dict):
        raise GraphRegistryError("langgraph.json must be a JSON object")

    config_doc: Dict[str, str] = {}
    graphs_section = payload.get("graphs") if "graphs" in payload else payload
    if not isinstance(graphs_section, dict):
        raise GraphRegistryError(
            "langgraph.json must define a 'graphs' object mapping ids to import targets"
        )

    for key, value in graphs_section.items():
        if not isinstance(key, str):
            raise GraphRegistryError("Graph identifiers must be strings")
        if isinstance(value, str):
            config_doc[key] = value.strip()
        elif (
            isinstance(value, dict)
            and "path" in value
            and isinstance(value["path"], str)
        ):
            config_doc[key] = value["path"].strip()
        else:
            raise GraphRegistryError(
                "Each graph entry must be a string import target or an object with a 'path' string"
            )

    return config_doc


def _import_graph(locator: str, *, base_path: Path) -> GraphInstance:
    module_target, attribute = _split_locator(locator)

    module = (
        _import_module_from_path(module_target, base_path)
        if _looks_like_path(module_target)
        else _import_module(module_target)
    )

    try:
        graph_obj = getattr(module, attribute)
    except AttributeError as exc:
        available = ", ".join(
            sorted(attr for attr in dir(module) if not attr.startswith("_"))
        )
        raise GraphRegistryError(
            f"Graph attribute '{attribute}' not found in module '{module.__name__}'. "
            f"Available attributes: {available}"
        ) from exc

    if isinstance(graph_obj, StateGraph):
        graph_obj = graph_obj.compile()

    if not isinstance(graph_obj, Pregel):
        raise GraphRegistryError(
            f"Reference '{locator}' did not resolve to a Pregel graph. Got {type(graph_obj)!r}."
        )

    return graph_obj


def _split_locator(locator: str) -> tuple[str, str]:
    if ":" not in locator:
        raise GraphRegistryError(
            "Graph locator must include a ':' separating module path and attribute name"
        )

    module_target, attribute = locator.rsplit(":", maxsplit=1)
    module_target = module_target.strip()
    attribute = attribute.strip()

    if not module_target or not attribute:
        raise GraphRegistryError(
            f"Invalid graph locator '{locator}'. Expected format 'module_or_path:attribute'."
        )

    return module_target, attribute


def _looks_like_path(module_target: str) -> bool:
    return module_target.endswith(".py") or any(
        sep in module_target for sep in ("/", "\\")
    )


def _import_module(module_path: str) -> ModuleType:
    _ensure_project_on_syspath()
    return importlib.import_module(module_path)


def _import_module_from_path(module_path: str, base_path: Path) -> ModuleType:
    candidate = Path(module_path)
    if not candidate.is_absolute():
        candidate = (base_path / candidate).resolve()

    if not candidate.exists():
        raise GraphRegistryError(
            f"Graph file '{module_path}' could not be found (resolved to {candidate})"
        )

    module_name = _build_module_name(candidate)
    spec = importlib.util.spec_from_file_location(module_name, candidate)
    if spec is None or spec.loader is None:
        raise GraphRegistryError(
            f"Unable to load module specification for '{candidate}'"
        )

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _build_module_name(path: Path) -> str:
    stem = path.stem.replace("-", "_")
    suffix = abs(hash(path.as_posix())) & 0xFFFFFFFF
    return f"orbit_graph_{stem}_{suffix:08x}"


def _ensure_project_on_syspath() -> None:
    project_str = str(_PROJECT_ROOT)
    if project_str not in sys.path:
        sys.path.append(project_str)
