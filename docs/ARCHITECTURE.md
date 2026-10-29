# Runtime architecture and API

The supported entrypoint is `agent_platform.api.main:app` with `langgraph.showcase.json`. The [README diagram](../README.md#how-execution-fits-together) shows the service boundaries. Browser/local-system experiments are separate graph paths; [browser design](BROWSER_DESIGN.md) covers their history.

## Follow one approval

1. The [Next.js proxy](https://github.com/Veer376/doot-agent-web/blob/main/src/app/api/langgraph/%5B..._path%5D/route.ts) forwards SDK requests to FastAPI. Provider secrets stay server-side.
2. [Thread routes](../packages/agent-platform/agent_platform/api/release_threads.py) verify ownership and use the existing PostgREST-backed table service. The default assistant selects `chat_agent`.
3. [Run creation](../packages/agent-platform/agent_platform/api/routes/runs.py) acquires a thread lock, stores run metadata, and starts a background task. A second active run on the thread receives 409.
4. The [worker](../packages/agent-platform/agent_platform/worker.py) executes the graph and writes events into Redis Streams. SSE returns stream IDs as event cursors; a client can rejoin from a cursor.
5. The [example graph](../packages/orbit-core/orbit_core/agents/showcase_agent.py) calls `inspect_tickets` and then `save_report`. `save_report` interrupts with the proposed Markdown before writing anything. [PostgreSQL checkpoint storage](../packages/orbit-core/orbit_core/clients/checkpointer.py) preserves graph state.
6. The UI submits `Command(resume=...)` with the decision mapped to the interrupt ID. Approval writes the report; rejection returns a declined result without a file write. A later thread-state request restores the conversation.

## Storage and lifecycle

| Data | Owner | Lifecycle |
| --- | --- | --- |
| Assistant/thread rows and metadata | PostgreSQL via PostgREST | Persist in the local database volume |
| Graph checkpoints | LangGraph PostgreSQL saver | Persist independently of the API process |
| Run status/metadata | Redis | 24-hour retention |
| Run events | Redis Streams | Approximately 5,000 events per run (Redis approximate trimming), with the retention window |
| Active execution | Background task inside the FastAPI process | Ends on API-process exit |
| Approved report | `.doot/reports` host bind mount | Remains until explicitly removed |

Checkpoint persistence is distinct from durable scheduling. The worker is not a distributed queue and does not automatically resume unfinished work after an API restart. Replay is limited by Redis retention. These are useful next steps for a production runtime, not current guarantees.

## Supported API surface

| Area | Routes used by the web quickstart |
| --- | --- |
| Assistants | `POST /assistants/search`, `GET /assistants/{id}`, `GET /assistants/{id}/schemas` |
| Threads | `POST /threads`, `POST /threads/search`, `GET/PATCH /threads/{id}` |
| Checkpoints | `GET /threads/{id}/state`, `POST /threads/{id}/history` |
| Runs | `POST /threads/{id}/runs/stream`, `GET /threads/{id}/runs`, `GET /threads/{id}/runs/{run_id}` |
| Stream control | `GET /threads/{id}/runs/{run_id}/stream`, `POST /threads/{id}/runs/{run_id}/cancel` |
| Local configuration | `GET /`, `GET /models` |

Open http://127.0.0.1:5000/docs for request schemas after startup. Test the local API without a model call:

```sh
curl --fail http://127.0.0.1:5000/
curl --fail -H 'Authorization: Bearer local' -H 'Content-Type: application/json' \
  -d '{}' http://127.0.0.1:5000/assistants/search
python3 scripts/smoke_api.py
```

The documented SDK-compatible subset is narrower than LangGraph Platform. State editing, branching, cron, arbitrary assistant creation and some search filters remain unfinished in historical services and are not a compatibility claim. In particular, metadata filtering is not implemented by the retained thread-table search. Unmounted endpoints return 404.

## Identity and deployment boundary

`DOOT_LOCAL_MODE=true` accepts the explicit local demo session and supplies the isolated bootstrap identity. PostgreSQL/PostgREST/Redis remain internal to Compose; only the localhost API port is published. This profile is for local evaluation.

The retained Supabase-backed auth path verifies bearer tokens with Supabase Auth. A hosted multi-user deployment, per-tool authorization, tenant isolation, resource limits and a durable scheduler need independent validation before exposing a service publicly. Human approval in the example governs the report write; it is not a shell/browser sandbox.

## Model adapters and upstream boundaries

The model factory has Google, OpenAI and Anthropic adapters. The default image and recorded live run use Google. Optional adapters need additional dependencies and provider configuration, with no cross-provider quality claim.

The thread/runtime service code includes adaptations of LangChain's runtime; browser utilities derive from browser-use; the web derives from Open Agent Platform. [NOTICE](../NOTICE.md) records licenses and attribution. The [verification record](VALIDATION.md) states which parts have actually run.
