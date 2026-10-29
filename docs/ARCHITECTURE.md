# Supported release API

The release entrypoint is `agent_platform.api.main:app`, with `langgraph.showcase.json` as graph configuration.

Supported: assistant listing/details/schema; thread create/search/get/metadata patch/latest state/history; run create+SSE, list/get, event replay/join and cancellation. Run state and metadata belong to the backend; the web is a client. Redis event IDs are SSE cursors. Concurrent runs on one thread are rejected. Approval interrupts persist in PostgreSQL and resume through `Command(resume=...)`.

Unsupported endpoints return 404 rather than pretending compatibility. The older service modules contain unfinished APIs (state editing, branching, cron and some filters). They remain source/history evidence, not the supported contract. Search metadata filtering is not implemented in the older table service. Historical APIs using LangGraph's private runtime modules are not mounted by the release entrypoint.

PostgREST reuses the existing `assistants` and `threads` table services. The local bootstrap supplies only the isolated demo identity. The existing Supabase migration is retained. Supabase-backed deployments now verify bearer tokens via Supabase Auth, but hosted multi-user deployment is not a validated release mode.

The model factory has Google, OpenAI and Anthropic adapters; the quickstart and live validation use Google. Additional adapters need their optional dependency extras and provider keys; no cross-provider quality claim is made.
