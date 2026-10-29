# Release validation — 29 October 2026

Verified locally on macOS with Python 3.13.12, Node.js 22, PostgreSQL 18, Redis 7 and PostgREST 16.5. The supported Compose profile pins PostgreSQL 16; Docker is not installed on this machine, so an actual Compose build/run remains unverified.

- Five deterministic tests pass: fixture counts, approval/resume, rejection without a write, explicit local-session auth, missing hosted auth rejection.
- Web TypeScript check and production build passed. Next build performs the TypeScript check separately; historical lint debt remains and lint is not a claimed passing gate.
- Live Gemini tool calls inspected six synthetic tickets, produced exact category/priority counts, paused at a persisted approval interrupt, and wrote a 511-byte Markdown report only after approval.
- Browser verification exercised the compiled web UI against the custom backend, approved the write, then reloaded the page and observed the restored conversation and saved-report confirmation.
- Original browser automation demo retained at the user's request. It is a historical workflow, separate from the new synthetic-data verification example.

The live check uses the user's existing provider key privately; keys and real database credentials are not in the release tree. Source/history secret audits and publishing state are recorded in the private release checkpoint outside both repositories.

Limitations: no production concurrency benchmark, queue durability claim, browser-agent regression suite or multi-user deployment verification. The original FastAPI implementation mixed local and private runtime APIs; the release mounts only the supported endpoints described in ARCHITECTURE.md. Historical modules remain available as source with their upstream license notices.
