"""Unit tests for translation_checker.

Covers all five measurement categories plus the public ``check_translation``
API and the CLI exit codes. Both PASS and FAIL scenarios are exercised.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# Add scripts/quality to sys.path for the import under test
SCRIPTS = Path(__file__).resolve().parents[1] / "quality"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

# Add scripts/tests/ so _helpers is importable
TESTS_DIR = Path(__file__).resolve().parent
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

from translation_checker import (  # noqa: E402
    DEFAULT_MIN_SCORE,
    _measure_facts,
    _measure_paragraphs,
    _measure_repetition,
    _measure_sentence_lengths,
    _measure_translation_tells,
    check_translation,
    main,
)

from _quality_helpers import clean_post_body, tiny_post_body, write_text  # noqa: E402


# ---------------------------------------------------------------------------
# Translation tells
# ---------------------------------------------------------------------------


def test_translation_tells_clean_body_low_penalty() -> None:
    body = clean_post_body()
    deduction, hits = _measure_translation_tells(body)
    # Clean body should hit at most '또한' 1~2 times → small penalty.
    assert deduction < 10, f"unexpected penalty on clean body: {deduction}, hits={hits}"


def test_translation_tells_heavy_body_high_penalty() -> None:
    body = tiny_post_body()
    deduction, hits = _measure_translation_tells(body)
    assert deduction >= 20, f"heavy AI body should deduct >= 20, got {deduction}"
    labels = {h["label"] for h in hits}
    # Every tell type we care about should appear at least once.
    assert any("직역투" in lbl for lbl in labels)
    assert any("회피" in lbl for lbl in labels)
    assert any("또한" in lbl for lbl in labels)


def test_translation_tells_en_blocklist_charged() -> None:
    body = (
        "In this article we will discuss X. As mentioned above, the following "
        "points matter. It is worth noting that AI is changing everything."
    )
    deduction, hits = _measure_translation_tells(body)
    assert deduction >= 20, f"EN blocklist should be charged: {deduction}, {hits}"
    labels = {h["label"] for h in hits}
    assert any("영문 잔존" in lbl for lbl in labels)


# ---------------------------------------------------------------------------
# Repetition
# ---------------------------------------------------------------------------


def test_repetition_charges_repeated_words() -> None:
    body = " ".join(["spacex"] * 20) + " hello"
    tokens = [t.lower() for t in body.split()]
    body_chars = len(body)
    deduction, hits = _measure_repetition(tokens, body_chars)
    assert deduction >= 5
    # "spacex" should be flagged (it is a 5+ per-1000 word); the exact penalty
    # varies with body length. We just check that it's present.
    assert any(h["word"] == "spacex" for h in hits)


def test_repetition_ignores_short_body() -> None:
    body = "안녕하세요. 오늘은 좋은 날입니다."
    tokens = [t.lower() for t in body.split()]
    body_chars = len(body)
    deduction, _ = _measure_repetition(tokens, body_chars)
    assert deduction == 0


# ---------------------------------------------------------------------------
# Sentence lengths
# ---------------------------------------------------------------------------


def test_sentence_lengths_healthy_body_no_penalty() -> None:
    # Each sentence is intentionally 30-60 chars (no whitespace) so it
    # falls in the healthy range. Mixing sentence lengths keeps the rhythm
    # check happy.
    body = (
        "이 문장은 적당한 길이로 작성되어 가독성이 좋습니다. "
        "보통 30에서 80자 정도의 한국어 문장이 읽기 편안합니다. "
        "이 정도 길이라면 문제없이 쾌적하게 읽을 수 있습니다. "
        "너무 짧거나 너무 길면 가독성이 떨어지기 마련입니다."
    )
    deduction, metrics, issues = _measure_sentence_lengths(body)
    assert deduction == 0, f"healthy body deducted {deduction}: {issues}"
    assert metrics["total"] >= 4
    assert issues == []


def test_sentence_lengths_too_many_short_penalised() -> None:
    body = " ".join(["짧은 문장."] * 30)
    deduction, metrics, issues = _measure_sentence_lengths(body)
    assert deduction > 0
    assert "짧은 문장" in issues[0]


def test_sentence_lengths_too_many_long_penalised() -> None:
    # Build a sentence that's clearly > 200 chars. Each "가" is 1 char and
    # we add ~220 of them.
    long_sent = "가" * 220 + "."
    assert len(long_sent) > 200, "test fixture should be > 200 chars"
    body = long_sent + " " + long_sent + " " + long_sent + "."
    deduction, metrics, issues = _measure_sentence_lengths(body)
    assert deduction > 0, f"long-sentence body should deduct, got {deduction}"
    assert any("긴 문장" in i for i in issues)


# ---------------------------------------------------------------------------
# Paragraphs
# ---------------------------------------------------------------------------


def test_paragraphs_penalises_long_paragraphs() -> None:
    lines = [f"이것은 단락 테스트 {i}번 줄입니다." for i in range(7)]
    body = "\n".join(lines)
    deduction, issues, suggestions = _measure_paragraphs(body)
    assert deduction > 0
    assert any("5줄" in i for i in issues)


def test_paragraphs_advice_includes_split_hint() -> None:
    lines = [f"줄 {i}" for i in range(6)]
    body = "\n".join(lines)
    _, _, suggestions = _measure_paragraphs(body)
    assert any("3줄" in s for s in suggestions)


# ---------------------------------------------------------------------------
# Facts
# ---------------------------------------------------------------------------


def test_facts_skipped_without_source_url() -> None:
    body = "$1,000,000 같은 가격이 나왔다."
    deduction, issues, _ = _measure_facts(body, "")
    assert deduction == 0
    assert any("원문 URL 미제공" in i for i in issues)


def test_facts_no_numbers_no_penalty() -> None:
    body = "단순한 텍스트 본문, 수치 없음."
    deduction, _, _ = _measure_facts(body, "https://example.com/no-such-url-12345.invalid/")
    assert deduction == 0


# ---------------------------------------------------------------------------
# End-to-end scoring
# ---------------------------------------------------------------------------


def test_check_translation_clean_post_passes(tmp_path: Path) -> None:
    post = write_text(tmp_path / "post.md", f"---\ntitle: t\n---\n\n{clean_post_body()}")
    result = check_translation(post, source_url="")
    assert result["threshold"] == DEFAULT_MIN_SCORE
    # The clean post should always pass; the AI body should always fail.
    assert result["pass"], result
    assert result["score"] >= DEFAULT_MIN_SCORE


def test_check_translation_ai_tells_fail(tmp_path: Path) -> None:
    post = write_text(tmp_path / "post.md", f"---\ntitle: t\n---\n\n{tiny_post_body()}")
    result = check_translation(post, source_url="")
    assert not result["pass"]
    assert result["score"] < DEFAULT_MIN_SCORE
    assert any("직역투" in i or "회피" in i or "또한" in i for i in result["issues"])


def test_check_translation_missing_file_zero(tmp_path: Path) -> None:
    result = check_translation(tmp_path / "nope.md")
    assert result["score"] == 0
    assert not result["pass"]
    assert any("missing" in i for i in result["issues"])


def test_check_translation_empty_body_zero(tmp_path: Path) -> None:
    post = write_text(tmp_path / "post.md", "---\ntitle: t\n---\n")
    result = check_translation(post)
    assert result["score"] == 0
    assert not result["pass"]


def test_check_translation_threshold_override(tmp_path: Path) -> None:
    post = write_text(tmp_path / "post.md", f"---\ntitle: t\n---\n\n{clean_post_body()}")
    # Set threshold to 1 — even clean body passes easily.
    result = check_translation(post, source_url="", min_score=1)
    assert result["threshold"] == 1
    assert result["pass"]


def test_check_translation_metrics_includes_breakdown(tmp_path: Path) -> None:
    post = write_text(tmp_path / "post.md", f"---\ntitle: t\n---\n\n{tiny_post_body()}")
    result = check_translation(post)
    bd = result["metrics"]["deduction_breakdown"]
    assert "translation_tells" in bd
    assert "repetition" in bd
    assert "sentence_lengths" in bd
    assert "paragraphs" in bd
    assert "facts" in bd
    assert "total" in bd
    # Total should equal 100 - score (capped at 0)
    assert bd["total"] == 100 - result["score"]


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def test_cli_passes_on_clean_body(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    post = write_text(tmp_path / "post.md", f"---\ntitle: t\n---\n\n{clean_post_body()}")
    rc = main(["--post", str(post)])
    captured = capsys.readouterr()
    assert rc == 0
    assert "PASS" in captured.out
    assert "translation score" in captured.out


def test_cli_fails_on_ai_body(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    post = write_text(tmp_path / "post.md", f"---\ntitle: t\n---\n\n{tiny_post_body()}")
    rc = main(["--post", str(post)])
    captured = capsys.readouterr()
    assert rc == 1
    assert "FAIL" in captured.out


def test_cli_json_output_machine_readable(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    post = write_text(tmp_path / "post.md", f"---\ntitle: t\n---\n\n{clean_post_body()}")
    rc = main(["--post", str(post), "--json"])
    captured = capsys.readouterr()
    parsed = json.loads(captured.out)
    assert isinstance(parsed["score"], int)
    assert "issues" in parsed
    assert "suggestions" in parsed
    assert "metrics" in parsed
    assert rc == 0
