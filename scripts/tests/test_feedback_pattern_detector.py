"""Unit tests for pattern_detector.py."""

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


def _risp_entry(event: str, stage_index: int, ts: datetime, session_id: str = "s1") -> dict:
    return {
        "timestamp": ts.isoformat(timespec="seconds"),
        "session_id": session_id,
        "event": event,
        "stage_index": stage_index,
        "stage_name": f"stage-{stage_index}",
        "stage_elapsed_s": 5.0,
        "message": "ok",
    }


def test_detect_infinite_loops_flags_repeated_starts(tmp_workspace):
    workspace, _ = tmp_workspace
    now = datetime.now(KST)
    entries = [
        _risp_entry("begin", 1, now - timedelta(minutes=i), session_id="loop-sess")
        for i in range(10)
    ]
    write_jsonl(workspace / "data" / "risp_progress.jsonl", entries)

    from feedback.pattern_detector import detect_infinite_loops

    findings = detect_infinite_loops(entries, threshold=5)
    assert any(f["session_id"] == "loop-sess" for f in findings)
    target = next(f for f in findings if f["session_id"] == "loop-sess")
    assert target["evidence"]["stage1_begin_count"] == 10


def test_detect_infinite_loops_ignores_short_sessions(tmp_workspace):
    workspace, _ = tmp_workspace
    now = datetime.now(KST)
    entries = [
        _risp_entry("begin", 1, now - timedelta(minutes=i), session_id="quiet-sess")
        for i in range(2)
    ]
    from feedback.pattern_detector import detect_infinite_loops

    findings = detect_infinite_loops(entries, threshold=5)
    assert findings == []


def test_detect_stage_repeats_flags_failed_audits(tmp_workspace):
    workspace, _ = tmp_workspace
    state = {
        "schema_version": "1.0",
        "slug": "stuck-2026-06-07",
        "title": "Stuck job",
        "status": "RECEIVED",
        "created_at": "2026-06-07T10:00:00+09:00",
        "updated_at": "2026-06-07T10:00:00+09:00",
        "notes": [
            {"timestamp": "2026-06-07T10:00:01+09:00", "text": "audit failed"},
            {"timestamp": "2026-06-07T10:00:02+09:00", "text": "audit failed"},
            {"timestamp": "2026-06-07T10:00:03+09:00", "text": "audit failed"},
        ],
    }
    write_json(workspace / "data" / "workflow-runs" / "stuck-2026-06-07.json", state)

    from feedback.pattern_detector import detect_stage_repeats

    findings = detect_stage_repeats(workspace / "data" / "workflow-runs", threshold=3)
    assert any(f["slug"] == "stuck-2026-06-07" for f in findings)


def test_detect_performance_regression_raises_on_20pct_increase(tmp_workspace):
    workspace, _ = tmp_workspace
    now = datetime.now(KST)
    entries = []
    # 30 baseline samples in the 28d-7d window (~10s each)
    for i in range(30):
        ts = now - timedelta(days=10 + i % 14)
        entries.append(_risp_entry("complete", 1, ts))
        entries[-1]["stage_elapsed_s"] = 10.0
    # 10 recent samples in last 7 days (~13s each)
    for i in range(10):
        ts = now - timedelta(days=i)
        entries.append(_risp_entry("complete", 2, ts))
        entries[-1]["stage_elapsed_s"] = 13.0
    write_jsonl(workspace / "data" / "risp_progress.jsonl", entries)

    from feedback.pattern_detector import detect_performance_regression

    findings = detect_performance_regression(entries)
    assert findings
    assert findings[0]["type"] == "performance_regression"
    assert findings[0]["evidence"]["delta_pct"] >= 20


def test_detect_performance_regression_skips_when_too_few_samples(tmp_workspace):
    workspace, _ = tmp_workspace
    now = datetime.now(KST)
    entries = [_risp_entry("complete", 1, now - timedelta(hours=i)) for i in range(2)]
    from feedback.pattern_detector import detect_performance_regression

    assert detect_performance_regression(entries) == []


def test_detect_quality_regression_flags_fallbacks_without_minimax(tmp_workspace):
    workspace, _ = tmp_workspace
    state = {
        "schema_version": "1.0",
        "slug": "fallback-2026-06-07",
        "title": "Fallbacks",
        "status": "RECEIVED",
        "created_at": "2026-06-07T10:00:00+09:00",
        "updated_at": "2026-06-07T10:00:00+09:00",
        "review": {"minimax_revisions": 0},
        "paths": {
            "image_plan": "data/image-plans/fallback-2026-06-07.json",
        },
    }
    plan = {
        "assets": [
            {"id": "a1", "model": "gpt-image-2", "attempts": [{"m": "gpt-image-2"}, {"m": "Minimax"}]},
            {"id": "a2", "model": "gpt-image-2", "attempts": [{"m": "gpt-image-2"}, {"m": "Minimax"}]},
        ]
    }
    write_json(workspace / "data" / "workflow-runs" / "fallback-2026-06-07.json", state)
    write_json(workspace / "data" / "image-plans" / "fallback-2026-06-07.json", plan)

    from feedback.pattern_detector import detect_quality_regression

    findings = detect_quality_regression(workspace / "data" / "workflow-runs")
    assert any(f["slug"] == "fallback-2026-06-07" for f in findings)


def test_detect_quality_regression_skips_when_minimax_present(tmp_workspace):
    workspace, _ = tmp_workspace
    state = {
        "schema_version": "1.0",
        "slug": "minimax-ok-2026-06-07",
        "title": "Healthy",
        "status": "RECEIVED",
        "created_at": "2026-06-07T10:00:00+09:00",
        "updated_at": "2026-06-07T10:00:00+09:00",
        "review": {"minimax_revisions": 2},
        "paths": {
            "image_plan": "data/image-plans/minimax-ok-2026-06-07.json",
        },
    }
    plan = {
        "assets": [
            {"id": "a1", "model": "gpt-image-2", "attempts": [{"m": "gpt-image-2"}, {"m": "Minimax"}]},
        ]
    }
    write_json(workspace / "data" / "workflow-runs" / "minimax-ok-2026-06-07.json", state)
    write_json(workspace / "data" / "image-plans" / "minimax-ok-2026-06-07.json", plan)

    from feedback.pattern_detector import detect_quality_regression

    assert detect_quality_regression(workspace / "data" / "workflow-runs") == []


def test_collect_alerts_writes_file(tmp_workspace):
    workspace, _ = tmp_workspace
    now = datetime.now(KST)
    entries = [
        _risp_entry("begin", 1, now - timedelta(minutes=i), session_id="loop")
        for i in range(7)
    ]
    write_jsonl(workspace / "data" / "risp_progress.jsonl", entries)

    result = run_cli(
        ["scripts/feedback/pattern_detector.py", "--since", "7d"],
        workspace=workspace,
    )
    assert result.returncode == 0
    alerts_path = workspace / "data" / "feedback" / "alerts.json"
    assert alerts_path.exists()
    payload = json.loads(alerts_path.read_text(encoding="utf-8"))
    assert payload["alert_count"] >= 1
    assert any(a["type"] == "infinite_loop" for a in payload["alerts"])
