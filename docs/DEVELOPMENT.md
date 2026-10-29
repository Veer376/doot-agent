# Native development

Python 3.13, uv, PostgreSQL 16+ (with pgcrypto), Redis 7+, and PostgREST 16.5 are required. Native development uses the same schema as Compose. Create an empty database and apply, in order: `deployments/local/00-auth.sql`, `supabase/migrations/20250924151716_init_core_schema.sql`, and `deployments/local/99-grants.sql`. Point PostgREST at that database with `PGRST_DB_ANON_ROLE=doot_local`; bind it to localhost.

```sh
uv sync --frozen
export DOOT_LOCAL_MODE=true
export POSTGREST_URL=http://127.0.0.1:53000
export POSTGRES_URL=postgresql://YOUR_USER@127.0.0.1:5432/YOUR_EMPTY_DEMO_DATABASE
export REDIS_URL=redis://127.0.0.1:6379/0
export GOOGLE_API_KEY=YOUR_OWN_KEY
uv run uvicorn agent_platform.api.main:app --host 127.0.0.1 --port 5000
```

Use an isolated database and Redis database. Keep keys in a local untracked environment file or process environment. To use a different model, install the corresponding adapter (`uv pip install 'langchain-openai>=0.3,<0.4'` or the Anthropic equivalent) and set `DOOT_MODEL` to a provider-prefixed ID.
