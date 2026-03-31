from __future__ import annotations

from typing import Any

from team_agents.cli_chat.ui import run_chat_ui


def main(argv: list[str] | None = None) -> int:
    """Entry point for the CLI chat UI."""
    run_chat_ui()
    return 0


__all__ = ["main", "run_chat_ui"]
