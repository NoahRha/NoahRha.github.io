"""Tests for the QUALITY_HOOK integration in blog_workflow_guard.

We do not run the full ``cmd_audit`` (it needs a real workflow state file),
but we do verify:
  * ``quality_hook_active()`` reads the env var correctly
  * ``run_quality_check_translation`` and ``run_quality_check_images`` are
    callable and return a tuple of (oks, errors, raw)
  * the subprocess they spawn is the correct one (translation_checker /
    image_checker with --json)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

TESTS_DIR = Path(__file__).resolve().parent
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

import blog_workflow_guard  # noqa: E402

from _quality_helpers import clean_post_body, make_png, tiny_post_body, write_text  # noqa: E402


def test_quality_hook_active_default_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("QUALITY_HOOK", raising=False)
    assert blog_workflow_guard.quality_hook_active() is False


@pytest.mark.parametrize("value", ["1", "true", "yes", "enabled", "on", "ENABLED"])
def test_quality_hook_active_truthy(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("QUALITY_HOOK", value)
    assert blog_workflow_guard.quality_hook_active() is True


def test_quality_hook_active_falsey(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("QUALITY_HOOK", "0")
    assert blog_workflow_guard.quality_hook_active() is False
    monkeypatch.setenv("QUALITY_HOOK", "off")
    assert blog_workflow_guard.quality_hook_active() is False
    monkeypatch.setenv("QUALITY_HOOK", "no")
    assert blog_workflow_guard.quality_hook_active() is False


def test_run_quality_check_translation_pass(tmp_path: Path) -> None:
    post = write_text(tmp_path / "post.md", f"---\ntitle: t\n---\n\n{clean_post_body()}")
    oks, errs, raw = blog_workflow_guard.run_quality_check_translation(post, "")
    assert any("quality translation" in o for o in oks)
    assert errs == []
    assert raw is not None
    assert raw["pass"] is True


def test_run_quality_check_translation_fail(tmp_path: Path) -> None:
    # Heavy AI-tell body — uses the same fixture as the unit tests.
    post = write_text(tmp_path / "post.md", f"---\ntitle: t\n---\n\n{tiny_post_body()}")
    oks, errs, raw = blog_workflow_guard.run_quality_check_translation(post, "")
    assert raw is not None
    assert raw["pass"] is False
    assert any("quality translation" in e for e in errs)


def test_run_quality_check_images_pass(tmp_path: Path) -> None:
    d = tmp_path / "imgs"
    d.mkdir()
    for i, color in enumerate([(255, 0, 0), (0, 255, 0), (0, 0, 255)]):
        make_png(d / f"a{i}.png", size=(1024, 1024), color=color)
    oks, errs, raw = blog_workflow_guard.run_quality_check_images(d, "hand-drawing", None)
    assert any("quality images" in o for o in oks)
    assert errs == []
    assert raw is not None


def test_run_quality_check_images_fail_bad_dir(tmp_path: Path) -> None:
    d = tmp_path / "empty"
    d.mkdir()
    oks, errs, raw = blog_workflow_guard.run_quality_check_images(d, "hand-drawing", None)
    assert raw is not None
    assert raw["pass"] is False
    assert any("quality images" in e for e in errs)


def test_run_quality_check_images_with_plan(tmp_path: Path) -> None:
    d = tmp_path / "imgs"
    d.mkdir()
    for i, color in enumerate([(255, 0, 0), (0, 255, 0), (0, 0, 255)]):
        make_png(d / f"a{i}.png", size=(1024, 1024), color=color)
    plan = tmp_path / "plan.json"
    plan.write_text(
        json.dumps(
            {
                "assets": [
                    {
                        "id": "cover",
                        "style": "hand-drawing",
                        "prompt": "Masterful hand-drawn ink editorial illustration of a rocket. No readable text.",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    oks, errs, raw = blog_workflow_guard.run_quality_check_images(d, "hand-drawing", plan)
    # Plan has the right style prefix ⇒ no style issues
    assert raw is not None
    style_misses = raw["global"]["style_consistency"].get("prompt_prefix_missing") or []
    assert style_misses == []
