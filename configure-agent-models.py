#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio

from langgraph_sdk import get_client

from doot_local.models import default_agent_model_context, local_models


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Persist a model policy into a LangGraph assistant context."
    )
    parser.add_argument("assistant_id")
    parser.add_argument(
        "--langgraph-url",
        default="http://127.0.0.1:2024",
        help="LangGraph API URL",
    )
    parser.add_argument(
        "--model",
        action="append",
        dest="models",
        help="Allowed application model ID; repeat to restrict the assistant",
    )
    parser.add_argument("--default", dest="default_model")
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    client = get_client(url=args.langgraph_url)
    assistant = await client.assistants.get(args.assistant_id)
    context = assistant.get("context")
    context = dict(context) if isinstance(context, dict) else {}

    discovered = local_models()
    defaults = default_agent_model_context(discovered)
    available_models = args.models or defaults["available_models"]
    default_model = args.default_model or defaults["default_model"]

    if default_model and default_model not in available_models:
        raise SystemExit("--default must also be present in the allowed model list")

    context.update(
        {
            "available_models": available_models,
            "default_model": default_model,
        }
    )
    updated = await client.assistants.update(args.assistant_id, context=context)
    print(updated["assistant_id"])
    print(updated.get("context") or {})


if __name__ == "__main__":
    asyncio.run(main())
