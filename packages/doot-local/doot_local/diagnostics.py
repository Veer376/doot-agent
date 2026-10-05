from __future__ import annotations

import json
import os
import re
import sqlite3
import threading
import time
import traceback
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable
import asyncio


_SENSITIVE_KEY = re.compile(
    r"(?:authorization|cookie|token|secret|password|api[_-]?key|credential)",
    re.IGNORECASE,
)


def _database_path() -> Path:
    configured = os.getenv("DOOT_DIAGNOSTICS_DB")
    if configured:
        return Path(configured).expanduser().resolve()
    # Keep telemetry outside the workspace. A LangGraph dev server with hot
    # reload enabled watches the repository; writing diagnostics inside it can
    # otherwise become a self-triggering reload loop.
    return (Path.home() / ".doot" / "diagnostics.sqlite3").resolve()


def _sanitize(value: Any, *, depth: int = 0) -> Any:
    if depth > 5:
        return "<max-depth>"
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            result[key_text] = (
                "<redacted>"
                if _SENSITIVE_KEY.search(key_text)
                else _sanitize(item, depth=depth + 1)
            )
        return result
    if isinstance(value, (list, tuple)):
        return [_sanitize(item, depth=depth + 1) for item in value[:100]]
    if isinstance(value, str):
        return value if len(value) <= 4000 else value[:4000] + "…"
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return _sanitize(repr(value), depth=depth + 1)


@dataclass(frozen=True)
class DiagnosticContext:
    thread_id: str | None = None
    run_id: str | None = None
    task_id: str | None = None
    checkpoint_id: str | None = None


def context_from_runtime(runtime: Any) -> DiagnosticContext:
    execution = getattr(runtime, "execution_info", None)
    if execution is None:
        return DiagnosticContext()
    return DiagnosticContext(
        thread_id=str(execution.thread_id) if execution.thread_id else None,
        run_id=str(execution.run_id) if execution.run_id else None,
        task_id=str(execution.task_id) if execution.task_id else None,
        checkpoint_id=str(execution.checkpoint_id)
        if execution.checkpoint_id
        else None,
    )


class DiagnosticsStore:
    def __init__(self, path: Path | str | None = None):
        self.path = Path(path or _database_path())
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=5)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA busy_timeout=5000")
        return connection

    def _initialize(self) -> None:
        with self._connect() as db:
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS diagnostic_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts REAL NOT NULL,
                    runtime_instance_id TEXT NOT NULL,
                    source TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    thread_id TEXT,
                    run_id TEXT,
                    task_id TEXT,
                    component TEXT,
                    message TEXT,
                    details_json TEXT NOT NULL
                )
                """
            )
            db.execute(
                "CREATE INDEX IF NOT EXISTS idx_diagnostic_thread_ts "
                "ON diagnostic_events(thread_id, ts DESC)"
            )
            db.execute(
                "CREATE INDEX IF NOT EXISTS idx_diagnostic_run_ts "
                "ON diagnostic_events(run_id, ts DESC)"
            )
            db.execute(
                "CREATE INDEX IF NOT EXISTS idx_diagnostic_kind_ts "
                "ON diagnostic_events(kind, ts DESC)"
            )

    def record(
        self,
        *,
        runtime_instance_id: str,
        source: str,
        kind: str,
        severity: str = "info",
        context: DiagnosticContext | None = None,
        component: str | None = None,
        message: str | None = None,
        details: Any = None,
        timestamp: float | None = None,
    ) -> int:
        ctx = context or DiagnosticContext()
        payload = json.dumps(_sanitize(details or {}), separators=(",", ":"))
        with self._lock, self._connect() as db:
            cursor = db.execute(
                """
                INSERT INTO diagnostic_events (
                    ts, runtime_instance_id, source, kind, severity,
                    thread_id, run_id, task_id, component, message, details_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    timestamp or time.time(),
                    runtime_instance_id,
                    source,
                    kind,
                    severity,
                    ctx.thread_id,
                    ctx.run_id,
                    ctx.task_id,
                    component,
                    message,
                    payload,
                ),
            )
            return int(cursor.lastrowid)

    def events(
        self,
        *,
        thread_id: str | None = None,
        run_id: str | None = None,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if thread_id:
            clauses.append("thread_id = ?")
            params.append(thread_id)
        if run_id:
            clauses.append("run_id = ?")
            params.append(run_id)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(max(1, min(int(limit), 1000)))
        with self._connect() as db:
            rows = db.execute(
                f"""
                SELECT * FROM diagnostic_events
                {where}
                ORDER BY ts DESC, id DESC
                LIMIT ?
                """,
                params,
            ).fetchall()
        return [self._row(row) for row in rows]

    def runtime_events_since(self, timestamp: float) -> list[dict[str, Any]]:
        with self._connect() as db:
            rows = db.execute(
                """
                SELECT * FROM diagnostic_events
                WHERE kind = 'runtime.started' AND ts >= ?
                ORDER BY ts ASC, id ASC
                """,
                (timestamp,),
            ).fetchall()
        return [self._row(row) for row in rows]

    @staticmethod
    def _row(row: sqlite3.Row) -> dict[str, Any]:
        item = dict(row)
        try:
            item["details"] = json.loads(item.pop("details_json"))
        except Exception:
            item["details"] = {"raw": item.pop("details_json", "")}
        return item


RUNTIME_INSTANCE_ID = uuid.uuid4().hex
RUNTIME_STARTED_AT = time.time()
STORE = DiagnosticsStore()


def record_event(
    kind: str,
    *,
    source: str = "backend",
    severity: str = "info",
    runtime: Any = None,
    context: DiagnosticContext | None = None,
    component: str | None = None,
    message: str | None = None,
    details: Any = None,
) -> int:
    return STORE.record(
        runtime_instance_id=RUNTIME_INSTANCE_ID,
        source=source,
        kind=kind,
        severity=severity,
        context=context or (context_from_runtime(runtime) if runtime is not None else None),
        component=component,
        message=message,
        details=details,
    )


def record_exception(
    kind: str,
    exc: BaseException,
    *,
    runtime: Any = None,
    component: str | None = None,
    details: Any = None,
) -> int:
    payload = {
        "exception_type": type(exc).__name__,
        "exception": str(exc) or repr(exc),
        "traceback": "".join(
            traceback.format_exception(type(exc), exc, exc.__traceback__, limit=20)
        ),
        "context": details or {},
    }
    return record_event(
        kind,
        severity="error",
        runtime=runtime,
        component=component,
        message=str(exc) or repr(exc),
        details=payload,
    )


async def async_record_event(*args, **kwargs) -> int:
    return await asyncio.to_thread(record_event, *args, **kwargs)


async def async_record_exception(*args, **kwargs) -> int:
    return await asyncio.to_thread(record_exception, *args, **kwargs)


def _first(events: Iterable[dict[str, Any]], kind: str) -> dict[str, Any] | None:
    candidates = [event for event in events if event.get("kind") == kind]
    return min(candidates, key=lambda event: event["ts"], default=None)


def classify_failure(
    raw_error: Any,
    *,
    thread_id: str | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    error_text = str(raw_error or "Unknown stream failure")
    lowered = error_text.lower()
    events = STORE.events(thread_id=thread_id, run_id=run_id, limit=250)
    run_started = _first(events, "run.started")
    effective_run_id = run_id or (run_started or {}).get("run_id")

    restarted = False
    restart_event: dict[str, Any] | None = None
    if run_started:
        runtime_events = STORE.runtime_events_since(float(run_started["ts"]))
        for event in runtime_events:
            if event["runtime_instance_id"] != run_started["runtime_instance_id"]:
                restarted = True
                restart_event = event
                break
        if run_started["runtime_instance_id"] != RUNTIME_INSTANCE_ID:
            restarted = True

    if restarted and (
        "cancel" in lowered
        or "stream" in lowered
        or "fetch" in lowered
        or "network" in lowered
        or "unknown" in lowered
    ):
        code = "runtime_restarted"
        title = "Agent runtime restarted"
        message = (
            "The local LangGraph runtime reloaded while this run was active, so the "
            "in-flight model step was cancelled. Retry the run after the runtime is stable."
        )
        retryable = True
    elif "cancellederror" in lowered or "cancelled" in lowered or "canceled" in lowered:
        code = "run_cancelled"
        title = "Run was cancelled"
        message = (
            "The run was cancelled before the model finished. This can happen when the "
            "runtime reloads, another run interrupts it, or the client explicitly stops it."
        )
        retryable = True
    elif "timeout" in lowered or "timed out" in lowered:
        code = "timeout"
        title = "Model request timed out"
        message = "The model did not complete within the configured timeout."
        retryable = True
    elif "429" in lowered or "rate limit" in lowered:
        code = "rate_limited"
        title = "Model provider rate limit"
        message = "The model provider temporarily rate-limited this request."
        retryable = True
    elif any(token in lowered for token in ("401", "403", "unauthorized", "forbidden")):
        code = "authentication"
        title = "Authentication failed"
        message = "The backend or model provider rejected the request credentials."
        retryable = False
    elif any(
        token in lowered
        for token in ("econnrefused", "connection refused", "fetch failed", "503", "502")
    ):
        code = "backend_unavailable"
        title = "Agent backend unavailable"
        message = "Doot could not reach one of the local runtime or model-proxy services."
        retryable = True
    else:
        code = "stream_failure"
        title = "Agent stream failed"
        message = error_text if error_text else "The agent stream ended unexpectedly."
        retryable = True

    return {
        "code": code,
        "title": title,
        "message": message,
        "technical_detail": error_text,
        "retryable": retryable,
        "thread_id": thread_id,
        "run_id": effective_run_id,
        "runtime_instance_id": RUNTIME_INSTANCE_ID,
        "run_runtime_instance_id": (run_started or {}).get("runtime_instance_id"),
        "restart_detected_at": (restart_event or {}).get("ts"),
        "events": events,
    }


record_event(
    "runtime.started",
    component="runtime",
    details={
        "pid": os.getpid(),
        "cwd": str(Path.cwd()),
        "python": os.sys.version.split()[0],
    },
)
