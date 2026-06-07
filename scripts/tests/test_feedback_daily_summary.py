"""Unit tests for daily_summary.py and dashboard.py."""

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


DATE = "2026-06-07"
SLUG = "summary-test-2026-06-07"


def _seed(workspace: Path) -> None:
    workflow = {
        "schema_version": "1.0",
        "slug": SLUG,
        "title": "Summary test",
        "source_url": "https://example.com/x",
        "status": "AUDIT_PREBUILD_OK",
        "created_at": f"{DATE}T10:00:00+09:00",
        "updated_at": f"{DATE}T12:30:00+09:00",
        "review": {
            "claude": "done",
            "gpt_fallback": "not_needed",
            "minimax": "done",
            "minimax_revisions": 2,
            "humanize_korean": "done",
            "poetry_rhythm": "done",
        },
    }
    write_json(workspace / "data" / "workflow-runs" / f"{SLUG}.json", workflow)

    retro = {
        "slug": SLUG,
        "retrospective_path": f"data/retrospectives/{DATE}/{SLUG}.md",
        "lessons_learned": ["Lesson A", "Lesson B"],
    }
    write_json(
        workspace / "data" / "retrospectives" / DATE / f"{SLUG}.json",
        retro,
    )

    risp = [
        {
            "timestamp": f"{DATE}T10:00:30+09:00",
            "session_id": "s1",
            "event": "begin",
            "stage_index": 1,
            "stage_name": "원문 분석",
            "stage_elapsed_s": 1.0,
            "message": "start",
        },
        {
            "timestamp": f"{DATE}T10:01:00+09:00",
            "session_id": "s1",
            "event": "complete",
            "stage_index": 1,
            "stage_name": "원문 분석",
            "stage_elapsed_s": 30.0,
            "message": "done",
        },
    ]
    write_jsonl(workspace / "data" / "risp_progress.jsonl", risp)

    signaling = [
        {"timestamp": f"{DATE}T10:02:00+09:00", "session_id": "s1", "level": "error", "message": "boom"},
        {"timestamp": f"{DATE}T10:03:00+09:00", "session_id": "s1", "level": "warn", "message": "warn1"},
    ]
    write_jsonl(workspace / "data" / "risp_signaling.log", signaling)

    tele_failures = [
        {"timestamp": f"{DATE}T10:04:00+09:00", "session_id": "s1", "telegram_error": "x"},
        {"timestamp": f"{DATE}T10:05:00+09:00", "session_id": "s1", "telegram_error": "y"},
    ]
    write_jsonl(workspace / "data" / "risp_telegram_failures.log", tele_failures)


def test_daily_summary_counts(tmp_workspace):
    workspace, _ = tmp_workspace
    _seed(workspace)
    from feedback.daily_summary import (
        workflows_on_date,
        retrospectives_on_date,
        signaling_summary,
        telegram_failure_count,
    )

    assert len(workflows_on_date(DATE)) == 1
    assert len(retrospectives_on_date(DATE)) == 1
    assert signaling_summary(DATE) == {"info": 0, "warn": 1, "error": 1}
    assert telegram_failure_count(DATE) == 2


def test_daily_summary_top_blockers(tmp_workspace):
    workspace, _ = tmp_workspace
    _seed(workspace)
    from feedback.daily_summary import top_blockers, workflows_on_date, risp_events_on_date

    from feedback.lib import load_risp_progress

    blockers = top_blockers(workflows_on_date(DATE), load_risp_progress())
    # signaling errors should appear; the single completed workflow should not.
    assert any("signaling error" in b for b in blockers)


def test_daily_summary_improvement_suggestions(tmp_workspace):
    workspace, _ = tmp_workspace
    _seed(workspace)
    from feedback.daily_summary import improvement_suggestions, workflows_on_date, retrospectives_on_date

    suggestions = improvement_suggestions(
        workflows_on_date(DATE),
        retrospectives_on_date(DATE),
        [],
        telegram_failures=5,
    )
    # 5 telegram failures + lessons seen
    assert any("Telegram failure" in s for s in suggestions)
    assert any("retrospective lessons" in s for s in suggestions)


def test_daily_summary_cli(tmp_workspace, capsys):
    workspace, _ = tmp_workspace
    _seed(workspace)
    result = run_cli(
        ["scripts/feedback/daily_summary.py", "--date", DATE],
        workspace=workspace,
    )
    assert result.returncode == 0, result.stderr
    body = (workspace / "data" / "daily-summary" / f"{DATE}.md").read_text(encoding="utf-8")
    assert f"# Daily summary — {DATE}" in body
    assert "Workflows started: 1" in body
    assert "Retrospectives written: 1" in body


def test_dashboard_text_output(tmp_workspace, capsys):
    workspace, _ = tmp_workspace
    _seed(workspace)
    result = run_cli(["scripts/feedback/dashboard.py"], workspace=workspace)
    assert result.returncode == 0, result.stderr
    assert "Blogger feedback dashboard" in result.stdout
    assert "7-day completion rate" in result.stdout
    assert "open alerts" in result.stdout


def test_dashboard_json_output(tmp_workspace):
    workspace, _ = tmp_workspace
    _seed(workspace)
    result = run_cli(
        ["scripts/feedback/dashboard.py", "--format", "json"],
        workspace=workspace,
    )
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["today"] == DATE
    assert "sections" in payload
    assert any("in-progress today" in s for s in payload["sections"][0])
