"""Aegra graph entrypoint for the existing local Doot graph.

Aegra loads graph entries from files with ``spec_from_file_location``.  The
main Doot graph module uses package-relative imports, so this tiny absolute-
import shim keeps the graph itself unchanged while giving Aegra a stable file
entrypoint.
"""

from doot_local.agent import graph

__all__ = ["graph"]
