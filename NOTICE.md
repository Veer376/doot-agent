# Attribution and license boundaries

Doot is maintained by Aryaveer. Backend source is distributed under Elastic License 2.0 (see LICENSE), with existing third-party permissions preserved. This is source-available, not a claim of OSI open-source licensing.

The API/service layer contains code adapted from LangChain's `langgraph-api` and `langgraph-runtime-inmem` distributions (Elastic-2.0). In particular the historical `agent_platform/graph.py`, `schema.py`, `utils.py`, and `api/services/` contain adapted server patterns/code. They must not be represented as wholly original or relicensed under MIT. Copyright and license terms of LangChain's source remain applicable. The release worker, supported run routes, local bootstrap and example graph include new Doot release work.

`packages/orbit-core/orbit_core/browser_use/` derives from browser-use, MIT; the upstream notice is preserved in LICENSES/browser-use-MIT.txt. It is retained for historical browser-agent work and is not used by the ticket-triage quickstart.

The companion web client derives from Open Agent Platform, MIT. See that repository's LICENSE and NOTICE.md. Installed dependencies retain their own licenses.
