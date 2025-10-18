"""Registry for loading and accessing graphs by ID. This will not handle the graph having context manager"""
from __future__ import annotations
from uuid import uuid4
import orjson
import importlib
import importlib.util
import json
import logging
import os
import sys
from pathlib import Path
from types import ModuleType
from typing import Callable, Dict, Iterable
from collections.abc import AsyncIterator, Callable
from langgraph.constants import CONFIG_KEY_CHECKPOINTER
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any, NamedTuple, TypeGuard, cast
from langgraph_sdk.schema import Config
from langgraph.graph import StateGraph
from langgraph.pregel import Pregel
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.store.base import BaseStore
from itertools import filterfalse
import inspect
import glob
import asyncio
from orbit_core.clients import checkpointer, store

logger = logging.getLogger("graph_registry")


GraphFactoryFromConfig = Callable[[Config], Pregel | StateGraph]
GraphFactory = Callable[[], Pregel | StateGraph]
GraphValue = Pregel | GraphFactory | GraphFactoryFromConfig


GRAPHS: dict[str, GraphValue] = {}
FACTORY_ACCEPTS_CONFIG: dict[str, bool] = {}


class GraphRegistryError(RuntimeError):
    """Raised when a graph cannot be loaded or is misconfigured."""


class GraphNotFoundError(KeyError):
    """Raised when a requested graph id is not present in the registry."""


def load_graphs_from_file(
    config_path: str | Path | None = None,
    *,
    root: Path | None = None,
    force: bool = False,
) -> int:
    """Populate the in-memory registry from a ``langgraph.json`` file.

    Args:
            config_path: Optional override path to the JSON manifest.
            root: The root directory for resolving relative paths. Required if config_path is not provided.
            force: When ``True`` the registry is rebuilt even if already populated.

    Returns:
            The number of graphs currently registered.
    """

    path = _resolve_config_path(config_path, root=root)

    if GRAPHS and not force:
        return len(GRAPHS)

    if not path.exists():
        logger.warning("langgraph.json not found at %s; registry remains empty", path)
        GRAPHS.clear()
        return 0

    try:
        config_doc = _load_config(path)
    except Exception as exc:  # pragma: no cover - logged and re-raised
        logger.exception("Failed to load graph configuration from %s", path)
        raise GraphRegistryError(str(exc)) from exc

    loaded: Dict[str, GraphValue] = {}
    for graph_id, value in config_doc.items():
        # Extract locator and optional metadata
        if isinstance(value, str):
            locator = value
            description = None
            graph_config = None
        elif isinstance(value, dict):
            locator = value["path"]
            description = value.get("description")
            graph_config = value.get("config")
        else:
            raise GraphRegistryError(
                f"Invalid value type for graph '{graph_id}': {type(value).__name__}"
            )

        try:
            graph = _import_graph(locator, base_path=path.parent)
            
            if callable(graph):
                FACTORY_ACCEPTS_CONFIG[graph_id] = len(inspect.signature(graph).parameters) > 0
                
        except Exception as exc:  # pragma: no cover - logged and re-raised
            logger.exception(
                "Unable to register graph '%s' from '%s'", graph_id, locator
            )
            raise GraphRegistryError(
                f"Failed to load graph '{graph_id}' from '{locator}'"
            ) from exc
        loaded[graph_id] = graph

    GRAPHS.clear()
    GRAPHS.update(loaded)

    logger.info("Registered %d graph(s) from %s", len(GRAPHS), path)
    return len(GRAPHS)


async def register_graph(
    graph_id: str,
    graph: GraphValue,
    config: dict | None,
    *,
    description: str | None = None,
) -> None:
    """Register a graph."""
    # from langgraph_runtime.database import connect
    # from langgraph_runtime.ops import Assistants

    await logger.ainfo(f"Registering graph with id '{graph_id}'", graph_id=graph_id)
    GRAPHS[graph_id] = graph
    
    if callable(graph):
        FACTORY_ACCEPTS_CONFIG[graph_id] = len(inspect.signature(graph).parameters) > 0

    from langgraph_runtime.retry import retry_db

    # @retry_db
    # async def register_graph_db():
    #     async with connect() as conn:
    #         graph_name = (
    #             getattr(graph, "name", None) if isinstance(graph, Pregel) else None
    #         )
    #         assistant_name = (
    #             graph_name
    #             if graph_name is not None and graph_name != "LangGraph"
    #             else graph_id
    #         )
    #         await Assistants.put(
    #             conn,
    #             str(uuid4()),
    #             graph_id=graph_id,
    #             metadata={"created_by": "system"},
    #             config=config or {},
    #             context={},
    #             if_exists="do_nothing",
    #             name=assistant_name,
    #             description=description,
    #         )

    # await register_graph_db()


def is_factory(
    value: GraphValue, graph_id: str
) -> TypeGuard[GraphFactoryFromConfig | GraphFactory]:
    return graph_id in FACTORY_ACCEPTS_CONFIG

# @asynccontextmanager
async def _generate_graph(value: Any) -> Any:
    """Yield a graph object regardless of its type."""
    if isinstance(value, Pregel):
        return value
    # elif hasattr(value, "__aenter__") and hasattr(value, "__aexit__"):
    #     async with value as ctx_value:
    #         yield ctx_value
    # elif hasattr(value, "__enter__") and hasattr(value, "__exit__"):
    #     with value as ctx_value:
    #         yield ctx_value
    elif asyncio.iscoroutine(value):
        return await value
    else:
        return value

def factory_accepts_config(
    value: GraphValue, graph_id: str
) -> TypeGuard[GraphFactoryFromConfig]:
    return FACTORY_ACCEPTS_CONFIG.get(graph_id, False)

# @asynccontextmanager
async def get_graph(
    graph_id: str,
    config: Config = {"configurable": {}},
    *,
    checkpointer: BaseCheckpointSaver = checkpointer,
    store: BaseStore = store,
) -> Pregel:
    """Return the runnable."""
    # from langgraph_api.utils import config as lg_config

    if graph_id not in GRAPHS:
        raise Exception(
            detail=f"Graph '{graph_id}' not found. Expected one of: {sorted(GRAPHS.keys())}",
        )

    value = GRAPHS[graph_id]
    if is_factory(value, graph_id):
        # config = lg_config.ensure_config(config)

        if store is not None:

            from langgraph._internal._constants import CONFIG_KEY_RUNTIME
            from langgraph.runtime import Runtime

            runtime = config["configurable"].get(CONFIG_KEY_RUNTIME)
            if runtime is None:
                patched_runtime = Runtime(store=store)
            elif isinstance(runtime, dict):
                patched_runtime = Runtime(**(runtime | {"store": store}))
            elif runtime.store is None:
                patched_runtime = cast(Runtime, runtime).override(store=store)
            else:
                patched_runtime = runtime
            config["configurable"][CONFIG_KEY_RUNTIME] = patched_runtime

        if checkpointer is not None and not config["configurable"].get(
            CONFIG_KEY_CHECKPOINTER
        ):
            config["configurable"][CONFIG_KEY_CHECKPOINTER] = checkpointer
        # var_child_runnable_config.set(config)
        value = value(config) if factory_accepts_config(value, graph_id) else value()
        
    try:
        graph_obj = await _generate_graph(value)
        
        if isinstance(graph_obj, StateGraph):
            graph_obj = graph_obj.compile()
        
        if not isinstance(graph_obj, Pregel): # | BaseRemotePregel
            raise Exception("Graph is not a Pregel instance")
        
        update = {
            "checkpointer": checkpointer,
            "store": store,
        }
        if graph_obj.name == "LangGraph":
            update["name"] = graph_id
        # if isinstance(graph_obj, BaseRemotePregel):
        #     update["config"] = config
        return graph_obj.copy(update=update)
    
    # finally:
        # var_child_runnable_config.set(None)
    except Exception as exc:
        raise exc

class GraphSpec(NamedTuple):
    """A graph specification.

    This is a definition of the graph that can be used to load the graph
    from a file or module.
    """

    id: str
    """The ID of the graph."""
    path: str | None = None
    module: str | None = None
    variable: str | None = None
    config: dict | None = None
    """The configuration for the graph.
    
    Contains information such as: tags, recursion_limit and configurable.
    
    Configurable is a dict containing user defined values for the graph.
    """
    description: str | None = None
    """A description of the graph"""


js_bg_tasks: set[asyncio.Task] = set()


def _graph_from_spec(spec: GraphSpec) -> GraphValue:
    """Return a graph from a spec."""
    # import the graph module
    if spec.module:
        module = importlib.import_module(spec.module)
    elif spec.path:
        try:
            modname = (
                spec.path.replace("/", "__")
                .replace(".py", "")
                .replace(" ", "_")
                .lstrip(".")
            )
            modspec = importlib.util.spec_from_file_location(modname, spec.path)
            if modspec is None:
                raise ValueError(f"Could not find python file for graph: {spec}")
            module = importlib.util.module_from_spec(modspec)
            sys.modules[modname] = module
            modspec.loader.exec_module(module)  # type: ignore[possibly-unbound-attribute]
        except ImportError as e:
            e.add_note(f"Could not import python module for graph:\n{spec}")
            raise
        except FileNotFoundError as e:
            e.add_note(f"Could not find python file for graph: {spec}")
            raise
    else:
        raise ValueError("Graph specification must have a path or module")

    if spec.variable:
        try:
            graph: GraphValue = module.__dict__[spec.variable]
        except KeyError as e:
            available = [k for k in module.__dict__ if not k.startswith("__")]
            suggestion = ""
            if available:
                likely = [
                    k
                    for k in available
                    if isinstance(module.__dict__[k], StateGraph | Pregel)
                ]
                if likely:
                    prefix = spec.module or spec.path
                    likely_ = "\n".join(
                        [f"\t- {prefix}:{k}" if prefix else k for k in likely]
                    )
                    suggestion = (
                        f"\nDid you mean to use one of the following?\n{likely_}"
                    )
                elif available:
                    suggestion = (
                        f"\nFound the following exports: {', '.join(available)}"
                    )

            raise ValueError(
                f"Could not find graph '{spec.variable}' in '{spec.path}'. "
                f"Please check that:\n"
                f"1. The file exports a variable named '{spec.variable}'\n"
                f"2. The variable name in your config matches the export name{suggestion}"
            ) from e
        if callable(graph):
            sig = inspect.signature(graph)
            if not sig.parameters:
                pass
            elif len(sig.parameters) != 1:
                raise ValueError(
                    f"Graph factory function '{spec.variable}' in module '{spec.path}' must take exactly one argument, a RunnableConfig"
                )
        elif isinstance(graph, StateGraph):
            graph = graph.compile()
        elif isinstance(graph, Pregel):
            # We don't want to fail real deployments, but this will help folks catch unnecessary custom components
            # before they deploy
            if os.getenv("API_VARIANT") == "local_dev":
                has_checkpointer = isinstance(graph.checkpointer, BaseCheckpointSaver)
                has_store = isinstance(graph.store, BaseStore)
                if has_checkpointer or has_store:
                    components = []
                    if has_checkpointer:
                        components.append(
                            f"checkpointer (type {type(graph.checkpointer)})"
                        )
                    if has_store:
                        components.append(f"store (type {type(graph.store)})")
                    component_list = " and ".join(components)

                    raise ValueError(
                        f"Heads up! Your graph '{spec.variable}' from '{spec.path}' includes a custom {component_list}. "
                        f"With LangGraph API, persistence is handled automatically by the platform, "
                        f"so providing a custom {component_list} here isn't necessary and will be ignored when deployed.\n\n"
                        f"To simplify your setup and use the built-in persistence, please remove the custom {component_list} "
                        f"from your graph definition. If you are looking to customize which postgres database to connect to,"
                        " please set the `POSTGRES_URI` environment variable."
                        " See https://langchain-ai.github.io/langgraph/cloud/reference/env_var/#postgres_uri_custom for more details."
                    )

        else:
            raise ValueError(
                f"Variable '{spec.variable}' in module '{spec.path}' is not a Graph or Graph factory function"
            )
    else:
        # find the graph in the module
        # - first look for a compiled graph (Pregel)
        # - if not found, look for a Graph and compile it
        for _, member in inspect.getmembers(module):
            if isinstance(member, Pregel):
                graph = member
                break
        else:
            for _, member in inspect.getmembers(module):
                if isinstance(member, StateGraph):
                    graph = member.compile()
                    break
            else:
                raise ValueError(
                    f"Could not find a Graph in module at path: {spec.path}"
                )

    return graph


def _load_graph_config_from_env() -> dict | None:
    """Return graph config from env."""
    config_str = os.getenv("LANGGRAPH_CONFIG")
    if not config_str:
        return None
    try:
        config_per_id = orjson.loads(config_str)
    except orjson.JSONDecodeError as e:
        raise ValueError(
            "Provided environment variable LANGGRAPH_CONFIG must be a valid JSON object"
            f"\nFound: {config_str}"
        ) from e

    if not isinstance(config_per_id, dict):
        raise ValueError(
            "Provided environment variable LANGGRAPH_CONFIG must be a JSON object"
            f"\nFound: {config_str}"
        )

    return config_per_id


async def collect_graphs_from_env(register: bool = False) -> None:
    """Return graphs from env."""

    paths_str = os.getenv("LANGSERVE_GRAPHS")
    config_per_graph = _load_graph_config_from_env() or {}

    if paths_str:
        print("Loading graphs from LANGSERVE_GRAPHS")
        specs = []
        # graphs-config can be either a mapping from graph id to path where the graph
        # is defined or graph id to a dictionary containing information about the graph.
        try:
            print("Got paths_str of type: ", type(paths_str))
            graphs_config = orjson.loads(paths_str)
            print("Graph_config: ", graphs_config)
        except orjson.JSONDecodeError as e:
            raise ValueError(
                "LANGSERVE_GRAPHS must be a valid JSON object."
                f"\nFound: {paths_str}"
                "\n The LANGSERVE_GRAPHS environment variable is typically set"
                'from the "graphs" field in your configuration (langgraph.json) file.'
            ) from e

        for key, value in graphs_config.items():
            if isinstance(value, dict) and "path" in value:
                source = value["path"]
            elif isinstance(value, str):
                source = value
            else:
                msg = (
                    f"Invalid value '{value}' for graph '{key}'. "
                    "Expected a string or a dictionary. "
                    "If a string, it should be the path to the graph definition. "
                    "For example: '/path/to/graph.py:graph_variable' "
                    "or 'my.module:graph_variable'. "
                    "If a dictionary, then it needs to contains a `path` key with the "
                    "path to the graph definition."
                    "It can also contains additional configuration for the graph; "
                    "e.g., `description`."
                    "For example: {'path': '/path/to/graph.py:graph_variable', "
                    "'description': 'My graph'}"
                )
                raise TypeError(msg)

            try:
                path_or_module, variable = source.rsplit(":", maxsplit=1)
            except ValueError as e:
                raise ValueError(
                    f"Invalid path '{value}' for graph '{key}'."
                    " Did you miss a variable name?\n"
                    " Expected one of the following formats:"
                    " 'my.module:variable_name' or '/path/to/file.py:variable_name'"
                ) from e

            graph_config = config_per_graph.get(key, {})
            description = (
                value.get("description", None) if isinstance(value, dict) else None
            )

            # Module syntax uses `.` instead of `/` to separate directories
            if "/" in path_or_module:
                path = path_or_module
                module_ = None
            else:
                path = None
                module_ = path_or_module

            specs.append(
                GraphSpec(
                    key,
                    module=module_,
                    path=path,
                    variable=variable,
                    config=graph_config,
                    description=description,
                )
            )
    else:
        specs = [
            GraphSpec(
                id=graph_path.split("/")[-1].replace(".py", ""),
                path=graph_path,
                config=config_per_graph.get(
                    graph_path.split("/")[-1].replace(".py", "")
                ),
            )
            for graph_path in glob.glob("/graphs/*.py")
        ]

    def is_js_spec(x: GraphSpec) -> bool:
        # return is_js_path(x.path)
        return False

    js_specs = list(filter(is_js_spec, specs))
    py_specs = list(filterfalse(is_js_spec, specs))

    for spec in specs:
        graph = _graph_from_spec(spec)
        if register:
            await register_graph(
                spec.id, graph, spec.config, description=spec.description
            )


def _resolve_config_path(
    config_path: str | Path | None, *, root: Path | None = None
) -> Path:
    if config_path is not None:
        return Path(config_path).expanduser().resolve()

    env_path = os.getenv("LANGGRAPH_SPEC_PATH")
    if env_path:
        return Path(env_path).expanduser().resolve()

    if root is None:
        raise ValueError(
            "Either 'config_path' or 'root' must be provided. "
            "The 'root' parameter is used to locate the default 'langgraph.json' file."
        )

    return (root / "langgraph.json").resolve()


def _load_config(path: Path) -> Dict[str, str | dict]:
    """Load graph configuration from langgraph.json file.

    Returns:
        Dictionary mapping graph IDs to either:
        - A string locator (e.g., "./path/to/graph.py:graph")
        - A dict with 'path', 'description', 'config', etc.
    """
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)

    if not isinstance(payload, dict):
        raise GraphRegistryError("langgraph.json must be a JSON object")

    config_doc: Dict[str, str | dict] = {}
    graphs_section = payload.get("graphs") if "graphs" in payload else payload
    if not isinstance(graphs_section, dict):
        raise GraphRegistryError(
            "langgraph.json must define a 'graphs' object mapping ids to import targets"
        )

    for key, value in graphs_section.items():
        if not isinstance(key, str):
            raise GraphRegistryError("Graph identifiers must be strings")

        if isinstance(value, str):
            # Simple string locator
            config_doc[key] = value.strip()
        elif isinstance(value, dict):
            # Dict with 'path' and optional 'description', 'config', etc.
            if "path" not in value or not isinstance(value["path"], str):
                raise GraphRegistryError(
                    f"Graph '{key}' dict must contain a 'path' string"
                )
            config_doc[key] = value
        else:
            raise GraphRegistryError(
                f"Each graph entry must be a string import target or an object with a 'path' string. "
                f"Got {type(value).__name__} for graph '{key}'"
            )

    return config_doc


def _import_graph(locator: str, *, base_path: Path) -> GraphValue:
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

    # if isinstance(graph_obj, StateGraph):
    #     graph_obj = graph_obj.compile()

    # if not isinstance(graph_obj, Pregel):
    #     raise GraphRegistryError(
    #         f"Reference '{locator}' did not resolve to a Pregel graph. Got {type(graph_obj)!r}."
    #     )

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
