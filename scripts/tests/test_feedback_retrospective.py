"""Unit tests for retrospective.py."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# Add scripts/feedback to sys.path for the import under test
SCRIPTS = Path(__file__).resolve().parents[1] / "feedback"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

# Add scripts/tests/ so _helpers is importable
TESTS_DIR = Path(__file__).resolve().parent
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

from _helpers import REPO_ROOT, run_cli, write_json, write_jsonl  # noqa: E402

import feedback.retrospective as retro_mod  # noqa: E402


SAMPLE_SLUG = "test-retro-2026-06-07"


def _seed_workflow(workspace: Path, *, slug: str = SAMPLE_SLUG) -> None:
    state = {
        "schema_version": "1.0",
        "slug": slug,
        "title": "Test retrospective",
        "source_url": "https://example.com/article",
        "style": "hand-drawing",
        "mode": "blog-sns",
        "status": "RECEIVED",
        "created_at": "2026-06-07T11:02:11+09:00",
        "updated_at": "2026-06-07T11:02:11+09:00",
        "paths": {
            "post": f"content/posts/{slug}.md",
            "sns": f"content/social/{slug}-sns.md",
            "image_dir": f"static/images/{slug}",
            "image_plan": f"data/image-plans/{slug}.json",
        },
        "required_gates": ["source_url_locked", "post_file_exists"],
        "review": {
            "claude": "pending",
            "gpt_fallback": "pending",
        },
        "notes": [],
    }
    write_json(workspace / "data" / "workflow-runs" / f"{slug}.json", state)


def _seed_risp(workspace: Path, slug: str = SAMPLE_SLUG) -> None:
    entries = [
        {
            "timestamp": "2026-06-07T11:02:30+09:00",
            "session_id": "sess-1",
            "event": "begin",
            "stage_index": 1,
            "stage_name": "원문 분석",
            "stage_elapsed_s": 1.0,
            "message": f"slug {slug} start",
        },
        {
            "timestamp": "2026-06-07T11:02:40+09:00",
            "session_id": "sess-1",
            "event": "complete",
            "stage_index": 1,
            "stage_name": "원문 분석",
            "stage_elapsed_s": 10.0,
            "message": f"slug {slug} done",
        },
    ]
    write_jsonl(workspace / "data" / "risp_progress.jsonl", entries)


def _seed_image_plan(workspace: Path, slug: str = SAMPLE_SLUG) -> None:
    plan = {
        "assets": [
            {
                "id": "cover",
                "model": "gpt-image-2",
                "status": "reviewed",
                "output_path": f"static/images/{slug}/{slug}-cover.png",
                "aspect_ratio": "1:1",
                "prompt": "hand-drawing cover",
                "attempts": [{"model": "gpt-image-2"}, {"model": "Minimax"}],
                "review": {"claude": "done"},
            },
            {
                "id": "threads",
                "model": "gpt-image-2",
                "status": "reviewed",
                "output_path": f"static/images/{slug}/{slug}-threads-comic.png",
                "aspect_ratio": "1:1",
                "prompt": "hand-drawing threads",
                "attempts": [{"model": "gpt-image-2"}],
                "review": {"claude": "done"},
            },
        ]
    }
    write_json(workspace / "data" / "image-plans" / f"{slug}.json", plan)


def test_render_markdown_includes_all_sections(tmp_workspace):
    workspace, lib = tmp_workspace
    _seed_workflow(workspace)
    _seed_risp(workspace)
    _seed_image_plan(workspace)

    from feedback.retrospective import render_markdown
    from feedback.lib import load_image_plan, load_risp_progress, load_workflow_state

    workflow = load_workflow_state(SAMPLE_SLUG)
    plan = load_image_plan(SAMPLE_SLUG)
    progress = load_risp_progress()

    body = render_markdown(SAMPLE_SLUG, workflow, progress, plan, {"success": 0, "failure": 0})

    assert "# Retrospective: test-retro-2026-06-07" in body
    assert "## Audit gates" in body
    assert "## Review fields" in body
    assert "## Stage breakdown (from RISP progress)" in body
    assert "## Image plan" in body
    assert "## Telegram / SNS publish outcomes" in body
    assert "## Lessons learned (auto-extracted)" in body
    assert "Minimax 0회" in body  # auto-extracted lesson


def test_stage_breakdown_computes_durations(tmp_workspace):
    workspace, _ = tmp_workspace
    _seed_workflow(workspace)
    _seed_risp(workspace)
    from feedback.retrospective import stage_breakdown
    from feedback.lib import load_risp_progress

    stages = stage_breakdown(load_risp_progress())
    assert stages
    assert stages[0]["stage_index"] == 1
    assert stages[0]["began_at"] == "2026-06-07T11:02:30+09:00"
    assert stages[0]["completed_at"] == "2026-06-07T11:02:40+09:00"
    assert stages[0]["duration_s"] == pytest.approx(10.0)


def test_detect_stuck_point(tmp_workspace):
    from feedback.retrospective import detect_stuck_point

    stages = [
        {"began_at": "2026-06-07T11:00:00+09:00", "completed_at": None, "stage_name": "초안"},
    ]
    assert detect_stuck_point(stages) == "초안"
    assert detect_stuck_point([]) is None
    assert (
        detect_stuck_point(
            [
                {
                    "began_at": "2026-06-07T11:00:00+09:00",
                    "completed_at": "2026-06-07T11:00:05+09:00",
                    "stage_name": "초안",
                }
            ]
        )
        is None
    )


def test_image_model_stats_with_fallbacks(tmp_workspace):
    workspace, _ = tmp_workspace
    _seed_workflow(workspace)
    _seed_image_plan(workspace)
    from feedback.retrospective import image_model_stats
    from feedback.lib import load_image_plan

    stats = image_model_stats(load_image_plan(SAMPLE_SLUG))
    assert stats["assets_total"] == 2
    assert stats["by_model"]["gpt-image-2"] == 2
    assert stats["fallback_assets"]  # cover had 2 attempts


def test_extract_lessons_catches_missing_minimax(tmp_workspace):
    workspace, _ = tmp_workspace
    _seed_workflow(workspace)
    _seed_image_plan(workspace)
    from feedback.lib import load_image_plan, load_workflow_state
    from feedback.retrospective import extract_lessons

    workflow = load_workflow_state(SAMPLE_SLUG)
    plan = load_image_plan(SAMPLE_SLUG)
    lessons = extract_lessons(workflow, [], plan, {"success": 0, "failure": 0})
    assert any("Minimax" in lesson for lesson in lessons)
    assert any("humanize-korean" in lesson for lesson in lessons)


def test_cli_generate_writes_markdown_and_sidecar(tmp_workspace, capsys):
    workspace, _ = tmp_workspace
    _seed_workflow(workspace)
    _seed_risp(workspace)
    _seed_image_plan(workspace)

    result = run_cli(
        [
            "scripts/feedback/retrospective.py",
            "generate",
            "--slug",
            SAMPLE_SLUG,
        ],
        workspace=workspace,
    )
    assert result.returncode == 0, result.stderr
    out_dir = workspace / "data" / "retrospectives" / "2026-06-07"
    assert (out_dir / f"{SAMPLE_SLUG}.md").exists()
    assert (out_dir / f"{SAMPLE_SLUG}.json").exists()
    body = (out_dir / f"{SAMPLE_SLUG}.md").read_text(encoding="utf-8")
    assert "## Lessons learned" in body


def test_cli_generate_all_processes_every_slug(tmp_workspace):
    workspace, _ = tmp_workspace
    _seed_workflow(workspace, slug="alpha-2026-06-07")
    _seed_workflow(workspace, slug="beta-2026-06-07")
    result = run_cli(
        ["scripts/feedback/retrospective.py", "generate", "--slug", "__all__"],
        workspace=workspace,
    )
    assert result.returncode == 0
    out_dir = workspace / "data" / "retrospectives" / "2026-06-07"
    assert (out_dir / "alpha-2026-06-07.md").exists()
    assert (out_dir / "beta-2026-06-07.md").exists()


def test_cli_generate_update_state_patches_workflow(tmp_workspace):
    workspace, _ = tmp_workspace
    _seed_workflow(workspace)
    _seed_risp(workspace)
    result = run_cli(
        [
            "scripts/feedback/retrospective.py",
            "generate",
            "--slug",
            SAMPLE_SLUG,
            "--update-state",
        ],
        workspace=workspace,
    )
    assert result.returncode == 0
    state = json.loads(
        (workspace / "data" / "workflow-runs" / f"{SAMPLE_SLUG}.json").read_text(encoding="utf-8")
    )
    assert "retrospective_path" in state
    assert "lessons_learned" in state
    assert isinstance(state["lessons_learned"], list)


def test_cli_generate_rejects_missing_slug(tmp_workspace):
    workspace, _ = tmp_workspace
    result = run_cli(
        [
            "scripts/feedback/retrospective.py",
            "generate",
            "--slug",
            "this-slug-does-not-exist",
        ],
        workspace=workspace,
    )
    # SLUG_RE only allows a-z, 0-9, hyphens. The slug we passed is valid
    # syntax; the script should reject it because no workflow state exists.
    assert result.returncode == 1
    assert "not found" in result.stdout


def test_cli_stats_filters_recent_window(tmp_workspace):
    workspace, _ = tmp_workspace
    _seed_workflow(workspace)
    result = run_cli(
        ["scripts/feedback/retrospective.py", "stats", "--since", "7d"],
        workspace=workspace,
    )
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["window"] == "7d"
    assert payload["workflow_count"] == 1
