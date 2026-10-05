import json

from doot_local import diagnostics


def test_classifies_runtime_restart_after_cancel(monkeypatch, tmp_path):
    store = diagnostics.DiagnosticsStore(tmp_path / "diagnostics.sqlite3")
    monkeypatch.setattr(diagnostics, "STORE", store)
    monkeypatch.setattr(diagnostics, "RUNTIME_INSTANCE_ID", "runtime-new")

    context = diagnostics.DiagnosticContext(thread_id="thread-1", run_id="run-1")
    store.record(
        runtime_instance_id="runtime-old",
        source="backend",
        kind="run.started",
        context=context,
        timestamp=100,
    )
    store.record(
        runtime_instance_id="runtime-new",
        source="backend",
        kind="runtime.started",
        timestamp=101,
    )

    result = diagnostics.classify_failure(
        "CancelledError()", thread_id="thread-1", run_id="run-1"
    )

    assert result["code"] == "runtime_restarted"
    assert result["retryable"] is True
    assert result["run_runtime_instance_id"] == "runtime-old"
    assert result["runtime_instance_id"] == "runtime-new"


def test_classifies_timeout_without_restart(monkeypatch, tmp_path):
    store = diagnostics.DiagnosticsStore(tmp_path / "diagnostics.sqlite3")
    monkeypatch.setattr(diagnostics, "STORE", store)
    monkeypatch.setattr(diagnostics, "RUNTIME_INSTANCE_ID", "runtime-one")

    context = diagnostics.DiagnosticContext(thread_id="thread-1", run_id="run-1")
    store.record(
        runtime_instance_id="runtime-one",
        source="backend",
        kind="run.started",
        context=context,
        timestamp=100,
    )

    result = diagnostics.classify_failure(
        "Request timed out", thread_id="thread-1", run_id="run-1"
    )

    assert result["code"] == "timeout"
    assert result["retryable"] is True


def test_redacts_sensitive_diagnostic_payloads(tmp_path):
    store = diagnostics.DiagnosticsStore(tmp_path / "diagnostics.sqlite3")
    store.record(
        runtime_instance_id="runtime-one",
        source="frontend",
        kind="client.test",
        details={
            "authorization": "Bearer secret",
            "nested": {"api_key": "abc", "safe": "visible"},
        },
    )

    [event] = store.events(limit=1)
    assert event["details"]["authorization"] == "<redacted>"
    assert event["details"]["nested"]["api_key"] == "<redacted>"
    assert event["details"]["nested"]["safe"] == "visible"
    json.dumps(event)
