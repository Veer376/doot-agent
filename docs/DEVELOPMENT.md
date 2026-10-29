# Setup and development

Start with the [backend + web quickstart](../README.md#run-it-locally). The default graph is `langgraph.showcase.json`; run commands from the backend repository root. Python is pinned to 3.13 by the root workspace. Node.js 22 and pnpm 9.15.4 are the web build versions.

## Local stack configuration

Copy `.env.example` to `.env` and set `GOOGLE_API_KEY` for a live run. `DOOT_MODEL` defaults to `google_genai:gemini-2.5-flash`. The Compose profile provides PostgreSQL 16, Redis 7, PostgREST 16.5, and the API image. Only API port 5000 is published, on `127.0.0.1`.

The web `.env.local.example` selects the local session and custom-platform UI. `LANGGRAPH_API_URL=http://127.0.0.1:5000` is the server-side upstream; the browser calls `http://127.0.0.1:3000/api/langgraph`. Keep provider keys in the backend environment.

```sh
docker compose -f compose.showcase.yml up --build -d --wait
python3 scripts/smoke_api.py
docker compose -f compose.showcase.yml logs --tail 100 api
```

The smoke check creates a labeled thread and tests assistant schemas, thread metadata, checkpoint reads, history, and Redis run listing. It makes no provider calls. Unit tests separately exercise graph approval and rejection with a scripted model.

Stop the stack with `docker compose -f compose.showcase.yml down`. This preserves named volumes. To intentionally reset the local demo database and event storage, run `docker compose -f compose.showcase.yml down -v`. Generated report files are a host bind mount and remain in `.doot/reports`.

## Native backend development

Install uv, PostgreSQL 16+ with `pgcrypto`, Redis 7+, and PostgREST 16.5. Use a dedicated empty database, not an existing application's database. Replace `YOUR_USER` below with your local PostgreSQL role; the role must be able to initialize the demo schema.

```sh
uv sync --frozen
createdb doot_showcase
export POSTGRES_URL=postgresql://YOUR_USER@127.0.0.1:5432/doot_showcase
psql "$POSTGRES_URL" -v ON_ERROR_STOP=1 -f deployments/local/00-auth.sql
psql "$POSTGRES_URL" -v ON_ERROR_STOP=1 -f supabase/migrations/20250924151716_init_core_schema.sql
psql "$POSTGRES_URL" -v ON_ERROR_STOP=1 -f deployments/local/99-grants.sql
```

In a separate terminal start an isolated Redis process:

```sh
redis-server --bind 127.0.0.1 --port 6380 --save '' --appendonly no
```

In another terminal, set the same database URI and start PostgREST:

```sh
export POSTGRES_URL=postgresql://YOUR_USER@127.0.0.1:5432/doot_showcase
PGRST_DB_URI="$POSTGRES_URL" PGRST_DB_ANON_ROLE=doot_local \
  PGRST_SERVER_HOST=127.0.0.1 PGRST_SERVER_PORT=53000 postgrest
```

Return to the first terminal. Set your provider key privately in the environment, then start the API:

```sh
export DOOT_LOCAL_MODE=true
export POSTGREST_URL=http://127.0.0.1:53000
export REDIS_URL=redis://127.0.0.1:6380/0
# Set GOOGLE_API_KEY in your shell environment before making model calls.
uv run uvicorn agent_platform.api.main:app --host 127.0.0.1 --port 5000
```

`POSTGRES_URL` is the direct checkpoint connection. `POSTGREST_URL` is the table API used by thread/assistant storage. Both must target the same database. Startup initializes checkpoint tables; the SQL bootstrap initializes application tables and the local demo identity.

The model factory also has OpenAI and Anthropic adapters. Native experiments can install `langchain-openai>=0.3,<0.4` or `langchain-anthropic>=0.3,<0.4` in the environment and use a provider-prefixed `DOOT_MODEL`. These adapters are not part of the default Compose image or the recorded Google validation.

## Web development and compiled checks

In `doot-agent-web`:

```sh
corepack pnpm install --frozen-lockfile
cp .env.local.example .env.local
corepack pnpm typecheck
corepack pnpm build
corepack pnpm start:local
```

`start:local` binds Next's production server to localhost. Rebuild after source changes. For development use `corepack pnpm dev --hostname 127.0.0.1` instead.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| API exits during startup | Read `docker compose -f compose.showcase.yml logs api postgres postgrest`; confirm database initialization succeeded |
| Port 5000 or 3000 is occupied | Stop your existing instance or choose a different published port; update the matching server proxy/API origin configuration |
| A model run errors | Check the backend's provider key, model ID, provider access and quota; never put the key in `NEXT_PUBLIC_*` variables |
| Browser UI cannot reach the API | Verify the API health response and `LANGGRAPH_API_URL`; use `127.0.0.1` consistently for the default local configuration |
| Old database state survives a rebuild | Named volumes are persistent; rebuilds do not reapply initialization SQL to existing volumes |
| A historical browser/local graph fails to import | Use the default showcase graph for the supported path; see [browser design](BROWSER_DESIGN.md) before restoring older entrypoints |

The [verification record](VALIDATION.md) states what has actually been run. Historical Kubernetes/cloud files are retained for inspection, not the local startup instructions.
