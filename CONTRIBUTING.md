# Contributing to Doot

The backend is the source of truth for architecture, demos, and the supported runtime contract. UI changes belong in [doot-agent-web](https://github.com/Veer376/doot-agent-web). Check [NOTICE](NOTICE.md) and [LICENSE](LICENSE) before reusing or contributing code.

## Start with the supported path

1. Follow the [quickstart](README.md#run-it-locally) and complete an approval/rejection cycle.
2. Read [Architecture](docs/ARCHITECTURE.md) and the source for the component you want to change.
3. Use Python 3.13 and `uv sync --frozen` for backend development. Run `uv run pytest` and `python3 scripts/check_docs.py` before opening a PR.
4. For API/storage changes, also start the local stack and run `python3 scripts/smoke_api.py`. For a model/tool behavior change, record the prompt, provider/model, expected behavior, and observed result without credentials or personal data.

The release test suite is intentionally scoped to the supported runtime. Historical scripts and browser/local-system experiments are not all runnable under the root environment. See [development setup](docs/DEVELOPMENT.md) and [verification boundaries](docs/VALIDATION.md).

## Find a bounded contribution

Useful work includes an isolated API regression case, a reproducible reconnect/cancellation problem, clearer setup for a platform you actually tested, or restoring one browser capability behind a separate configuration. [Browser design](docs/BROWSER_DESIGN.md) lists the concrete blockers to that last path.

For a larger API or agent redesign, open an issue describing the user-visible problem, current source path, and smallest working reproduction before implementing it. Small bug fixes can go directly to a PR.

## Make a reviewable change

Use a focused branch and describe the trigger, resulting behavior, and verification in the PR. Include screenshots or a short recording for visible UI/approval changes. Distinguish deterministic tests from live provider checks; do not present mock responses as real-model behavior. Add a regression test when the change alters behavior that can be checked meaningfully.

Keep provider keys, browser profiles, recorded sessions, generated reports, and local environment files out of commits. Preserve upstream notices and attribution. If a change touches both repositories, link the companion PR and state which commit/version was tested together.
