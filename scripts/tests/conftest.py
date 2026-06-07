"""Shared pytest fixtures for the feedback-loop test suite.

Each test uses an isolated temporary workspace so it cannot accidentally
mutate real `data/workflow-runs/`, `data/retrospectives/`, etc.

The trick: the feedback module reads paths from `feedback.lib` (e.g.
`WORKSPACE = Path("/Users/noah/.openclaw/workspace-blogger")`). Tests
monkeypatch those module-level constants to point at a tmp dir.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS_DIR))


def _reload_lib_with_workspace(workspace: Path):
    """Reload feedback.lib with WORKSPACE pointing at the tmp dir."""
    # Drop cached feedback modules so re-imports pick up the patched
    # workspace.
    for name in list(sys.modules):
        if name == "feedback" or name.startswith("feedback."):
            del sys.modules[name]

    import feedback.lib as lib  # type: ignore

    lib.WORKSPACE = workspace
    lib.WORKFLOW_DIR = workspace / "data" / "workflow-runs"
    lib.IMAGE_PLAN_DIR = workspace / "data" / "image-plans"
    lib.RETRO_DIR = workspace / "data" / "retrospectives"
    lib.ALERTS_DIR = workspace / "data" / "feedback"
    lib.DAILY_SUMMARY_DIR = workspace / "data" / "daily-summary"
    lib.RISP_PROGRESS = workspace / "data" / "risp_progress.jsonl"
    lib.RISP_SIGNALING = workspace / "data" / "risp_signaling.log"
    lib.RISP_TELEGRAM_FAILURES = workspace / "data" / "risp_telegram_failures.log"
    lib.SNS_PUBLISH_LOG = workspace / "data" / "sns_publish_log.jsonl"
    lib.SNS_V3_RUNS = workspace / "data" / "sns_v3_runs.jsonl"
    return lib


@pytest.fixture
def tmp_workspace(tmp_path):
    """Yield (workspace, lib) where lib has been reloaded with the tmp path."""
    workspace = tmp_path / "ws"
    workspace.mkdir()
    for sub in [
        "data/workflow-runs",
        "data/image-plans",
        "data/retrospectives",
        "data/feedback",
        "data/daily-summary",
    ]:
        (workspace / sub).mkdir(parents=True)

    lib = _reload_lib_with_workspace(workspace)

    # Re-import the script modules so they see the patched lib.
    import feedback.retrospective  # type: ignore
    import feedback.pattern_detector  # type: ignore
    import feedback.daily_summary  # type: ignore
    import feedback.dashboard  # type: ignore
    import feedback.memory_updater  # type: ignore

    yield workspace, lib
