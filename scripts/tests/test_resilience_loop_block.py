#!/usr/bin/env python3
"""
Track-A 2026-06-07 self-test: RISP pipeline의 무한 루프 차단 동작 검증.

검증 항목:
1. 동일 session_id로 blog_url 없이 호출 N회 반복 시, N회째에 BLOCKED_LOOP로 종료
2. blog_url과 함께 호출되면 cycle counter가 증가하지 않음
3. blocked return에 next_action이 포함되어 사용자가 다음 행동을 알 수 있음
4.ProgressTracker의 cycle_n이 jsonl 로그에 기록됨
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

# Make workspace-blogger importable
WORKSPACE = Path("/Users/noah/.openclaw/workspace-blogger")
sys.path.insert(0, str(WORKSPACE))
sys.path.insert(0, str(WORKSPACE / "scripts"))

from risp.orchestration.auto_blog_sns_pipeline import (  # noqa: E402
    CycleTracker,
    MAX_BLOCKED_CYCLES,
    run_pipeline,
)
from risp.signaling.progress import ProgressTracker  # noqa: E402


class TestResilienceLoopBlock(unittest.TestCase):
    """동일 session_id로 blog_url-미전달 호출을 N회 반복하면 BLOCKED."""

    def setUp(self):
        self.session_id = "resilience-loop-test-2026-06-07"
        self.mock_intake = MagicMock()
        self.mock_signaler = MagicMock()
        self.mock_state = MagicMock()
        # blog_url 없이 호출되므로 blog_creator가 호출됨. 항상 실패 반환.
        self.mock_blog = MagicMock(
            return_value={"success": False, "error": "blog_url required"}
        )
        self.mock_sns = MagicMock(return_value={"success": True})

        # CycleTracker는 인메모리 구현으로 격리.
        self.mock_cycle = MagicMock(spec=CycleTracker)
        self.mock_cycle.read.return_value = 0
        # bump는 카운터를 1씩 올리는 단순 in-memory 동작 흉내.
        self._bump_state = {"value": 0}

        def _bump(sid, increment=1):
            self._bump_state["value"] += increment
            return self._bump_state["value"]

        def _read(sid):
            return self._bump_state["value"]

        self.mock_cycle.read.side_effect = _read
        self.mock_cycle.bump.side_effect = _bump

    def _call_once(self):
        return run_pipeline(
            source_url="https://example.com/article",
            session_id=self.session_id,
            intake_func=self.mock_intake,
            signaler=self.mock_signaler,
            state_manager=self.mock_state,
            blog_creator=self.mock_blog,
            sns_publisher=self.mock_sns,
            cycle_tracker=self.mock_cycle,
            max_blocked_cycles=MAX_BLOCKED_CYCLES,
        )

    def test_first_three_calls_pass_through_with_blog_failure(self):
        """Calls 1~3: blog_creator가 실패 반환하지만 BLOCKED는 안 됨."""
        for i in range(MAX_BLOCKED_CYCLES):
            result = self._call_once()
            self.assertFalse(result.get("blocked"), f"call {i+1} should not be blocked")
            # blog_url 없음 → cycle 카운터가 bump 되어야 함
            self.assertEqual(self._bump_state["value"], i + 1)
        # 모든 호출이 BLOG_FAILED 같은 blog creator 실패로 끝나야 함
        self.mock_blog.assert_called()

    def test_fourth_call_is_blocked_loop(self):
        """4번째 호출은 BLOCKED_LOOP로 즉시 종료되어야 함."""
        # 3번 정상 통과
        for _ in range(MAX_BLOCKED_CYCLES):
            self._call_once()
        # 4번째는 차단
        result = self._call_once()
        self.assertTrue(result.get("blocked"), "4th call must be blocked")
        self.assertEqual(result.get("blocked_reason"), "BLOCKED_LOOP")
        self.assertIn("next_action", result)
        self.assertIn("source-blog-publisher", result["next_action"])
        # 차단 시 blog_creator는 호출되면 안 됨 (이미 차단됐으므로)
        before = self.mock_blog.call_count
        self._call_once()  # 5번째도 차단
        self.assertEqual(self.mock_blog.call_count, before)

    def test_blocked_return_includes_cycle_n_and_max(self):
        """차단 응답에 cycle_n과 max_cycles가 포함되어 디버깅이 쉬워야 함."""
        for _ in range(MAX_BLOCKED_CYCLES):
            self._call_once()
        result = self._call_once()
        self.assertEqual(result.get("cycle_n"), MAX_BLOCKED_CYCLES)
        self.assertEqual(result.get("max_cycles"), MAX_BLOCKED_CYCLES)

    def test_blocked_alerts_telegram_via_signaler(self):
        """차단 시 _signal로 텔레그램 알림이 발송되어야 함."""
        for _ in range(MAX_BLOCKED_CYCLES):
            self._call_once()
        self.mock_signaler.reset_mock()  # 마지막 호출의 신호만 검사
        result = self._call_once()
        self.assertTrue(result.get("blocked"))
        # signaler가 호출되었는지 (텔레그램 알림)
        self.assertTrue(self.mock_signaler.called)
        # 호출된 메시지 중 BLOCKED_LOOP 키워드 포함 확인
        all_signals = [str(c) for c in self.mock_signaler.call_args_list]
        self.assertTrue(
            any("BLOCKED_LOOP" in s for s in all_signals),
            f"Expected BLOCKED_LOOP in signaler calls, got: {all_signals}",
        )

    def test_blog_url_call_does_not_bump_cycle(self):
        """blog_url이 있는 정상 호출은 cycle을 증가시키지 않아야 함."""
        result = run_pipeline(
            source_url="https://example.com/article",
            session_id=self.session_id,
            intake_func=self.mock_intake,
            signaler=self.mock_signaler,
            state_manager=self.mock_state,
            blog_creator=self.mock_blog,
            sns_publisher=self.mock_sns,
            cycle_tracker=self.mock_cycle,
            blog_url="https://techllm.github.io/posts/test/",
            max_blocked_cycles=MAX_BLOCKED_CYCLES,
        )
        self.assertNotEqual(result.get("blocked"), True)
        # blog_url 전달 시 cycle은 bump되지 않음
        self.assertEqual(self._bump_state["value"], 0)
        # blog_creator는 호출되면 안 됨 (blog_url이 있으니 검증만)
        self.mock_blog.assert_not_called()

    def test_progress_tracker_writes_cycle_n_to_jsonl(self):
        """ProgressTracker._send()가 cycle_n을 jsonl에 기록해야 함."""
        import io
        from contextlib import redirect_stdout, redirect_stderr
        from risp.signaling import progress as progress_mod

        # 임시 jsonl 경로
        tmp_jsonl = tempfile.NamedTemporaryFile(
            mode="w", suffix=".jsonl", delete=False
        )
        tmp_jsonl.close()
        original_log = progress_mod.PROGRESS_LOG
        try:
            progress_mod.PROGRESS_LOG = Path(tmp_jsonl.name)
            tracker = ProgressTracker(
                "test-cycle-n-log", total_stages=2, label="CYCLE_TEST"
            )
            tracker.cycle_n = 7
            tracker.begin("first")
            tracker.complete("done")
            tracker.summary()

            lines = Path(tmp_jsonl.name).read_text(encoding="utf-8").splitlines()
            entries = [json.loads(l) for l in lines if l.strip()]
            self.assertTrue(entries, "jsonl should have entries")
            for e in entries:
                self.assertIn("cycle_n", e, f"missing cycle_n in entry: {e}")
        finally:
            progress_mod.PROGRESS_LOG = original_log
            try:
                os.unlink(tmp_jsonl.name)
            except Exception:
                pass

    def test_complete_resets_stage_index_to_zero(self):
        """complete() 호출 시 stage_index가 0으로 리셋되어 다음 begin이 1부터 시작."""
        tracker = ProgressTracker("test-reset", total_stages=3, label="RESET")
        tracker.begin("A")
        self.assertEqual(tracker.stage_index, 1)
        tracker.complete("done")
        # complete 후 stage_index는 0
        self.assertEqual(tracker.stage_index, 0)
        # 다시 begin하면 1부터 시작
        tracker.begin("B")
        self.assertEqual(tracker.stage_index, 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
