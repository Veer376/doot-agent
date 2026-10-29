# Verification record — 29 October 2026

## Automated checks

[Backend CI run 40872504461](https://github.com/Veer376/doot-agent/actions/runs/40872504461) passed at revision `5432839` with two jobs:

- **Backend:** frozen uv installation on Python 3.13; five deterministic release tests; all 65 repository-relative links across ten documents; Compose configuration parsing.
- **Compose integration:** built the actual API image and started the documented PostgreSQL 16, Redis 7, PostgREST 16.5, and FastAPI stack on Ubuntu. The smoke check read assistant schemas, created and patched a thread through PostgREST, read PostgreSQL-backed graph state/history, and listed runs through Redis. After restarting the API it retrieved the same thread and persisted metadata. No provider key or model calls were used. The job removed its volumes afterward.

The five deterministic tests cover fixture counts, graph approval/resume, rejection without a write, explicit local-session auth, and missing hosted auth rejection. The graph tests use a scripted model and in-memory checkpoints; they are not model-quality or PostgreSQL write benchmarks.

The web repository has its own [TypeScript and production-build workflow](https://github.com/Veer376/doot-agent-web/actions/workflows/release-checks.yml). [Web run 40872352702](https://github.com/Veer376/doot-agent-web/actions/runs/40872352702) passed TypeScript checking and the production build for canonical-link revision `95aedc3`; the local TypeScript check also passed. Historical lint debt remains separate from those gates.

Reproduce the backend checks:

```sh
uv sync --frozen
uv run pytest
python3 scripts/check_docs.py
docker compose -f compose.showcase.yml up --build -d --wait
python3 scripts/smoke_api.py --thread-file /tmp/doot-smoke-thread
docker compose -f compose.showcase.yml restart api
python3 scripts/smoke_api.py --thread-file /tmp/doot-smoke-thread --verify-existing
docker compose -f compose.showcase.yml down
```

The smoke check creates one labeled thread. It checks service integration and metadata persistence; approval behavior is checked separately below and in the deterministic graph tests.

## Recorded live validation

The release preparation previously ran the compiled web UI and backend natively on macOS with Python 3.13.12, Node.js 22, PostgreSQL 18, Redis 7 and PostgREST 16.5.

- A live Gemini run inspected six synthetic support tickets, produced the exact category/priority counts, and paused at a PostgreSQL-backed approval interrupt.
- After approval it wrote a 511-byte Markdown report. The UI was reloaded and restored the conversation and saved-report confirmation.
- [Approval/resume recording](assets/demos/approval-resume.mp4): two captures of the same real thread are joined, with the pause omitted. The data is synthetic; model/tool execution was live.

## Demo and documentation inspection

Both original lab recordings, the icon, architecture sketch and Gemini experiment images were copied into the canonical repository and checked against their original bytes. The additional browser recording and approval/resume clip are also here. [Provenance](PROVENANCE.md) records their origins.

The published GitHub README was opened in an isolated browser: both original video attachments render as players, the local images load, and the expected heading structure is present. The website responded successfully and its public interface was captured for the linked preview. Website reachability is separate from hosted-agent availability.

## Remaining boundaries

There is no published production-concurrency benchmark, durable queue guarantee, browser-agent regression score, or validated multi-user hosted deployment. The older browser entrypoint needs adapter/import repair and a controlled browser fixture before it belongs in the supported quickstart; see [browser design](BROWSER_DESIGN.md). Historical lab proposals are not treated as implemented features.
