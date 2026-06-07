"""Test helpers for the feedback-loop test suite.

`conftest.py` is loaded by pytest as a fixture provider, not as a regular
Python module, so test files cannot do `from .conftest import ...`. This
helper module lives next to conftest.py and exposes the small utilities
the tests need.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path("/Users/noah/.openclaw/workspace-blogger")
SCRIPTS_DIR = REPO_ROOT / "scripts"


def run_cli(
    args: list[str],
    cwd: Path | None = None,
    workspace: Path | None = None,
) -> subprocess.CompletedProcess:
    """Run a script with the given args via subprocess.

    If `workspace` is given, the subprocess is launched with
    FEEDBACK_WORKSPACE=workspace so the feedback module reads/writes the
    isolated test directory.
    """
    env = {**os.environ, "PYTHONPATH": str(SCRIPTS_DIR)}
    if workspace is not None:
        env["FEEDBACK_WORKSPACE"] = str(workspace)
    return subprocess.run(
        [sys.executable, *args],
        cwd=str(cwd or REPO_ROOT),
        capture_output=True,
        text=True,
        env=env,
    )


def write_jsonl(path: Path, entries: list[dict]) -> None:
    """Write a JSONL file with the given entries."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for entry in entries:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")


def write_json(path: Path, payload: dict) -> None:
    """Write a single JSON document."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
