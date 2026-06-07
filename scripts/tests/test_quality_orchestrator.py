"""Unit tests for review_orchestrator (2-stage review flow).

We do NOT call real CLIs in tests — the LLM stage is mocked by deleting
PATH entries. The translation + image stages run as normal subprocesses
(because the orchestrator itself is a thin shell that calls into them).
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "quality"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

TESTS_DIR = Path(__file__).resolve().parent
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

import review_orchestrator  # noqa: E402
from review_orchestrator import (  # noqa: E402
    cmd_check_images,
    cmd_check_translation,
    cmd_review_all,
    main,
)

from _quality_helpers import clean_post_body, make_png, tiny_post_body, write_text  # noqa: E402


# ---------------------------------------------------------------------------
# Stage 1: translation via orchestrator CLI
# ---------------------------------------------------------------------------


def test_orchestrator_check_translation_pass(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    post = write_text(tmp_path / "post.md", f"---\ntitle: t\n---\n\n{clean_post_body()}")
    rc = main(["check-translation", "--post", str(post)])
    captured = capsys.readouterr()
    assert rc == 0
    assert "translation" in captured.out


def test_orchestrator_check_translation_fail(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    post = write_text(tmp_path / "post.md", f"---\ntitle: t\n---\n\n{tiny_post_body()}")
    rc = main(["check-translation", "--post", str(post)])
    captured = capsys.readouterr()
    assert rc == 1
    assert "FAIL" in captured.out


# ---------------------------------------------------------------------------
# Stage 1: images via orchestrator CLI
# ---------------------------------------------------------------------------


def test_orchestrator_check_images_pass(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    d = tmp_path / "imgs"
    d.mkdir()
    for i, color in enumerate([(255, 0, 0), (0, 255, 0), (0, 0, 255)]):
        make_png(d / f"a{i}.png", size=(1024, 1024), color=color)
    rc = main(["check-images", "--image-dir", str(d), "--style", "hand-drawing"])
    captured = capsys.readouterr()
    assert rc == 0
    assert "PASS" in captured.out


def test_orchestrator_check_images_fail(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    d = tmp_path / "imgs"
    d.mkdir()
    p = make_png(d / "a.png", size=(640, 640), color=(100, 100, 100))
    rc = main(["check-images", "--image-dir", str(d), "--style", "hand-drawing"])
    captured = capsys.readouterr()
    assert rc == 1


# ---------------------------------------------------------------------------
# Stage 2: LLM wrapper behaviour when no CLI is available
# ---------------------------------------------------------------------------


def test_llm_skipped_when_no_cli(monkeypatch: pytest.MonkeyPatch) -> None:
    # Ensure neither claude nor openai is on PATH
    monkeypatch.setattr("shutil.which", lambda _: None)
    result = review_orchestrator._try_llm_review("dummy prompt")
    assert result["status"] == "skipped"
    assert "claude CLI not on PATH" in result["reason"]


# ---------------------------------------------------------------------------
# review-all: short-circuits on stage-1 fail, no LLM cost
# ---------------------------------------------------------------------------


def test_review_all_fails_on_translation_even_when_images_pass(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # Make LLM call always skipped so we know stage-2 did not save us.
    monkeypatch.setattr("shutil.which", lambda _: None)

    post = write_text(tmp_path / "post.md", f"---\ntitle: t\n---\n\n{tiny_post_body()}")
    d = tmp_path / "imgs"
    d.mkdir()
    for i, color in enumerate([(255, 0, 0), (0, 255, 0), (0, 0, 255)]):
        make_png(d / f"a{i}.png", size=(1024, 1024), color=color)

    rc = main(
        [
            "review-all",
            "--slug", "test-slug",
            "--post", str(post),
            "--image-dir", str(d),
            "--source-url", "",
            "--style", "hand-drawing",
        ]
    )
    captured = capsys.readouterr()
    assert rc == 1
    assert "FAIL" in captured.out
    assert "stage 1 failed" in captured.out or "translation" in captured.out


def test_review_all_passes_stage1_skips_llm_by_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr("shutil.which", lambda _: None)

    post = write_text(tmp_path / "post.md", f"---\ntitle: t\n---\n\n{clean_post_body()}")
    d = tmp_path / "imgs"
    d.mkdir()
    for i, color in enumerate([(255, 0, 0), (0, 255, 0), (0, 0, 255)]):
        make_png(d / f"a{i}.png", size=(1024, 1024), color=color)

    rc = main(
        [
            "review-all",
            "--slug", "test-slug",
            "--post", str(post),
            "--image-dir", str(d),
            "--source-url", "",
            "--style", "hand-drawing",
        ]
    )
    captured = capsys.readouterr()
    assert rc == 0
    assert "PASS" in captured.out
    assert "stage2 LLM:" in captured.out
    assert "skipped" in captured.out


def test_review_all_with_llm_attempts_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # Pretend claude is on PATH but make it return non-zero so we exercise the
    # gpt-fallback path (which we also stub out). Final result should be
    # 'failed' for stage 2 but stage 1 still PASS.
    def fake_which(name: str) -> str | None:
        if name == "claude":
            return "/usr/bin/claude"
        return None

    monkeypatch.setattr("shutil.which", fake_which)

    def fake_run(cmd, **kwargs):
        class R:
            returncode = 1
            stdout = ""
            stderr = "claude errored"
        return R()

    monkeypatch.setattr("subprocess.run", fake_run)

    post = write_text(tmp_path / "post.md", f"---\ntitle: t\n---\n\n{clean_post_body()}")
    d = tmp_path / "imgs"
    d.mkdir()
    for i, color in enumerate([(255, 0, 0), (0, 255, 0), (0, 0, 255)]):
        make_png(d / f"a{i}.png", size=(1024, 1024), color=color)

    rc = main(
        [
            "review-all",
            "--slug", "test-slug",
            "--post", str(post),
            "--image-dir", str(d),
            "--source-url", "",
            "--style", "hand-drawing",
            "--llm",
        ]
    )
    captured = capsys.readouterr()
    # Stage 1 passed, stage 2 attempted + failed ⇒ overall still PASS
    # (the orchestrator treats failed LLM as a non-fatal warning).
    assert rc == 0
    assert "stage2 LLM:" in captured.out
    assert "failed" in captured.out


# ---------------------------------------------------------------------------
# review-all: JSON output is machine-readable
# ---------------------------------------------------------------------------


def test_review_all_json_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr("shutil.which", lambda _: None)

    post = write_text(tmp_path / "post.md", f"---\ntitle: t\n---\n\n{clean_post_body()}")
    d = tmp_path / "imgs"
    d.mkdir()
    for i, color in enumerate([(255, 0, 0), (0, 255, 0), (0, 0, 255)]):
        make_png(d / f"a{i}.png", size=(1024, 1024), color=color)

    rc = main(
        [
            "review-all",
            "--slug", "test-slug",
            "--post", str(post),
            "--image-dir", str(d),
            "--source-url", "",
            "--style", "hand-drawing",
            "--json",
        ]
    )
    captured = capsys.readouterr()
    parsed = json.loads(captured.out)
    assert parsed["slug"] == "test-slug"
    assert "stage1" in parsed
    assert "stage2" in parsed
    assert "overall_pass" in parsed
    assert parsed["stage1"]["translation"]["pass"] is True
    assert parsed["stage1"]["images"]["pass"] is True
    assert rc == 0
