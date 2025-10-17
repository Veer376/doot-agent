from langgraph.types import Command, Send
from typing import cast
from langgraph.pregel import Pregel
from pydantic import create_model
from typing import Any
from pydantic import TypeAdapter


def map_cmd(cmd: dict) -> Command:
    goto = cmd.get("goto")
    if goto is not None and not isinstance(goto, list):
        goto = [cmd.get("goto")]

    update = cmd.get("update")
    if isinstance(update, tuple | list) and all(
        isinstance(t, tuple | list) and len(t) == 2 and isinstance(t[0], str)
        for t in cast(list, update)
    ):
        update = [tuple(t) for t in cast(list, update)]

    return Command(
        update=update,
        goto=(
            [
                it if isinstance(it, str) else Send(it["node"], it["input"])  # type: ignore[non-subscriptable]
                for it in goto
            ]
            if goto
            else None
        ),
        resume=cmd.get("resume"),
    )


def state_jsonschema(graph: Pregel) -> dict | None:
    fields: dict = {}
    for k in graph.stream_channels_list:
        v = graph.channels[k]
        try:
            create_model(k, __root__=(v.UpdateType, None)).model_json_schema()
            fields[k] = (v.UpdateType, None)
        except Exception:
            fields[k] = (Any, None)
    return create_model(graph.get_name("State"), **fields).model_json_schema()


EXCLUDED_CONFIG_SCHEMA = (
    "__pregel_checkpointer",
    "__pregel_store",
    "checkpoint_id",
    "checkpoint_ns",
    "thread_id",
)


def get_configurable_jsonschema(graph: Pregel) -> dict:
    """Get the JSON schema for the configurable part of the graph.

    Important: we only return the `configurable` part of the schema.

    The default get_config_schema method returns the entire schema (RunnableConfig),
    which includes other root keys like "max_concurrency", which we
    do not want to expose.

    Args:
        graph: The graph to get the schema for.

    Returns:
       The JSON schema for the configurable part of the graph.

    Whenever we no longer support langgraph < 0.6, we can remove this method
    in favor of graph.get_context_jsonschema().
    """
    # Otherwise, use the config_schema method.
    # TODO: Remove this when we no longer support langgraph < 0.6
    config_schema = graph.config_schema()  # type: ignore[deprecated]
    model_fields = getattr(config_schema, "model_fields", None) or getattr(
        config_schema, "__fields__", None
    )

    if model_fields is not None and "configurable" in model_fields:
        configurable = TypeAdapter(model_fields["configurable"].annotation)
        json_schema = configurable.json_schema()
        if json_schema:
            for key in EXCLUDED_CONFIG_SCHEMA:
                json_schema["properties"].pop(key, None)
        # The type name of the configurable type is not preserved.
        # We'll add it back to the schema if we can.
        if (
            hasattr(graph, "config_type")
            and graph.config_type is not None
            and hasattr(graph.config_type, "__name__")
        ):
            json_schema["title"] = graph.config_type.__name__
        return json_schema
    # If the schema does not have a configurable field, return an empty schema.
    return {}
