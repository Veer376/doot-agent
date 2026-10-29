# Browser-agent engineering notes

The original problem was browser work that required more than a chat response: identify the right element, interact with it, inspect the result, and choose the next tool. The [recordings](../README.md#demos) show that earlier workflow in real sessions. This page maps the design to the retained source and distinguishes it from today's supported local example.

## Perception: visual context plus actionable DOM

[perception.py](../packages/orbit-core/orbit_core/agents/browser_agent/perception.py) builds screenshot context and a numbered representation of interactive DOM elements. The screenshot provides layout; DOM labels give tools an element identity. The earlier experiments compared spatial clicks, DOM text, and mixed representations. The working observations are preserved in [the original lab notes](history/lab-architecture.md); they are design observations, not a controlled accuracy or latency benchmark.

[message_builder.py](../packages/orbit-core/orbit_core/agents/browser_agent/message_builder.py) assembles the current page snapshot, recent user messages, model responses, and tool results. Other perception classes are experiments; their presence does not establish equivalent working support.

## Tool availability follows context

[ToolRegistry](../packages/orbit-core/orbit_core/agents/browser_agent/toolkit/registry.py) records callable tools and optional availability predicates. `get_active_tools` builds a `FilterContext` from URL/domain, step, previous actions, and reserved tool names. [tools.py](../packages/orbit-core/orbit_core/agents/browser_agent/toolkit/tools.py) contains navigation, typing, extraction, and dropdown handling. For example, a dropdown interaction can reserve `select_dropdown_option` for the next decision instead of exposing it indiscriminately.

This is useful as a tool-selection design: compare a small context-relevant action set with binding every available tool. There is no published token-savings claim.

## Planning and recovery: design history

![Original browser-agent design sketch](assets/agentic_architecture.png)

The lab sketch explored a planner, scratchpad, browser executor, and replanning loop. It remains useful history, but the current browser graph does not implement every box. It retains a scratchpad state field and conditional error-message registry; the current message builder still has a dynamic-instructions TODO. The lab's multi-agent-company and MCP-builder descriptions were exploratory directions, not verified shipped features, and are not promoted as product capabilities.

## Runtime, approvals, and the web client

The current quickstart validates the graph/runtime boundary with a simpler workflow: model tool call → approval interrupt → checkpoint → explicit decision → persisted report. [Architecture](ARCHITECTURE.md) describes that working path. The original desktop recording includes Electron, which is outside the backend/web distribution.

## Reproduction boundary and next useful work

The historical browser entrypoint imports an absent `orbit_core.agents.llms` wrapper and assumes browser/runtime dependencies outside the default environment. It is not enabled in `langgraph.showcase.json`. Pointing the quickstart at the old `langgraph.json` is not a supported shortcut.

Useful follow-on work would restore a separately selectable browser graph using the current model factory, add a controlled local HTML fixture, and verify browser lifecycle/teardown and tool completion routing. A bounded task suite would then support real success/latency measurements. [benchmark/](../benchmark) retains task definitions and an older evaluator whose imports also need updating; no current benchmark score is claimed.

The historical files are preserved so an engineer can inspect the actual evolution rather than infer it from a demo alone.
