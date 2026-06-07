"""Unit tests for memory_updater.py and lib helpers."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "feedback"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

TESTS_DIR = Path(__file__).resolve().parent
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

from _helpers import run_cli, write_json, write_jsonl  # noqa: E402

KST = timezone(timedelta(hours=9))


def test_parse_since_accepts_common_units():
    from feedback.lib import parse_since, now_kst_iso, parse_iso_kst

    now = parse_iso_kst(now_kst_iso())
    for token, seconds in [("1h", 3600), ("1d", 86400), ("1w", 7 * 86400), ("1m", 30 * 86400)]:
        past = parse_since(token)
        assert (now - past).total_seconds() == pytest.approx(seconds, rel=0.01)


def test_parse_since_rejects_garbage():
    from feedback.lib import parse_since

    with pytest.raises(ValueError):
        parse_since("nonsense")


def test_is_terminal_status_distinguishes_states():
    from feedback.lib import is_terminal_status

    assert is_terminal_status("AUDIT_PREBUILD_OK")
    assert is_terminal_status("FAILED_SOMETHING")
    assert is_terminal_status("BLOCKED_LOOP")
    assert is_terminal_status("COMPLETED")
    assert not is_terminal_status("RECEIVED")
    assert not is_terminal_status("")


def test_iter_jsonl_skips_corrupt_lines(tmp_workspace):
    workspace, _ = tmp_workspace
    p = workspace / "data" / "risp_progress.jsonl"
    p.write_text(
        "\n".join(
            [
                "",
                json.dumps({"a": 1}),
                "{not-json}",
                json.dumps({"a": 2}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    from feedback.lib import iter_jsonl

    assert [e["a"] for e in iter_jsonl(p)] == [1, 2]


def test_extract_lessons_no_data_returns_baseline():
    from feedback.retrospective import extract_lessons

    workflow = {"review": {"minimax_revisions": 2, "humanize_korean": "done", "poetry_rhythm": "done"}}
    lessons = extract_lessons(workflow, [], None, {"success": 0, "failure": 0})
    assert lessons == ["이번 작업은 주요 게이트를 모두 통과함 — 회고 템플릿/가드 유지"]


def test_memory_updater_suggest_never_writes_memory(tmp_workspace, capsys):
    """memory_updater must NEVER touch MAMAVIS_MEMORY."""
    workspace, _ = tmp_workspace
    # Seed one alert so we have something to suggest.
    alerts = {
        "generated_at": "2026-06-07T12:00:00+09:00",
        "window_days": 7,
        "alert_count": 1,
        "alerts": [
            {
                "type": "infinite_loop",
                "severity": "high",
                "message": "session loop-sess restarted stage 1 10 times",
            }
        ],
    }
    write_json(workspace / "data" / "feedback" / "alerts.json", alerts)
    # Make sure MAMAVIS_MEMORY has a known mtime so we can detect writes.
    from feedback.lib import MAMAVIS_MEMORY

    original_mtime = MAMAVIS_MEMORY.stat().st_mtime
    original_content = MAMAVIS_MEMORY.read_text(encoding="utf-8")

    result = run_cli(
        ["scripts/feedback/memory_updater.py", "suggest"],
        workspace=workspace,
    )
    assert result.returncode == 0
    assert "Track C memory preview" in result.stdout

    # The mtime and content must be unchanged.
    assert MAMAVIS_MEMORY.stat().st_mtime == original_mtime
    assert MAMAVIS_MEMORY.read_text(encoding="utf-8") == original_content


def test_memory_updater_apply_dryrun_writes_preview_file(tmp_workspace):
    workspace, _ = tmp_workspace
    alerts = {
        "generated_at": "2026-06-07T12:00:00+09:00",
        "window_days": 7,
        "alert_count": 1,
        "alerts": [
            {
                "type": "infinite_loop",
                "severity": "high",
                "message": "session loop-sess restarted stage 1 10 times",
            }
        ],
    }
    write_json(workspace / "data" / "feedback" / "alerts.json", alerts)
    out = workspace / "preview.md"
    result = run_cli(
        [
            "scripts/feedback/memory_updater.py",
            "apply",
            "--output",
            str(out),
        ],
        workspace=workspace,
    )
    assert result.returncode == 0
    assert out.exists()
    body = out.read_text(encoding="utf-8")
    assert "Candidate lessons" in body
    assert "infinite_loop" in body
    assert "DO NOT commit" in body or "Do NOT commit" in body
