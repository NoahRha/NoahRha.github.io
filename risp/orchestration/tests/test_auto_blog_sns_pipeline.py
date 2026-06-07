#!/usr/bin/env python3
"""
TDD for the Unified RISP Auto Blog + SNS Pipeline

This is the final verification that the orchestrator that unifies both entry points
(direct chat and Obsidian "블로그 작성요청" button) properly implements RISP principles:
- Immediate Intake + ACK
- Proper state management
- Continuous signaling (no silence)
- Automatic progression to real SNS publishing
- Clear success/failure with next_action on errors
"""

import unittest
from unittest.mock import MagicMock, patch, call
from pathlib import Path
import tempfile
import json
import sys

# Match the pattern used by other successful risp tests
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from risp.orchestration.auto_blog_sns_pipeline import auto_publish_sns, run_pipeline


class TestAutoBlogSnsPipelineTDD(unittest.TestCase):
    """TDD suite for the single source of truth automatic pipeline."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.session_id = "2026-06-01-neuro-sns-001"
        self.source_url = "https://example.com/neuroethics-article"

        # Mocks for all external collaborators (RISP style)
        self.mock_intake = MagicMock()
        self.mock_signaler = MagicMock()
        self.mock_state_manager = MagicMock()
        self.mock_blog_creator = MagicMock()
        self.mock_sns_publisher = MagicMock()

        # Track-A 2026-06-07: cycle_tracker를 Mock으로 주입해서 디스크
        # 영속 상태(real session_id)와 분리한다. 테스트가 매번 깨끗한
        # 카운터로 시작하도록 한다.
        self.mock_cycle_tracker = MagicMock(spec=["read", "bump"])
        self.mock_cycle_tracker.read.return_value = 0
        self.mock_cycle_tracker.bump.return_value = 1

        # Default successful behaviors
        self.mock_blog_creator.return_value = {
            "success": True,
            "blog_url": "https://techllm.github.io/posts/neuroethics-embedded-ethicist-neuroscience-lab/",
            "slug": "neuroethics-embedded-ethicist-neuroscience-lab",
        }

        self.mock_sns_publisher.return_value = {
            "success": True,
            "results": {
                "threads": {"success": True, "post_url": "https://www.threads.net/post/18112598726505439"},
                "instagram": {"success": True, "post_id": "some_ig_id"},
            }
        }

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_immediate_risp_intake_on_entry(self):
        """The very first thing must be RISP Intake + ACK. No work before this."""
        run_pipeline(
            source_url=self.source_url,
            session_id=self.session_id,
            intake_func=self.mock_intake,
            signaler=self.mock_signaler,
            state_manager=self.mock_state_manager,
            blog_creator=self.mock_blog_creator,
            sns_publisher=self.mock_sns_publisher,
            cycle_tracker=self.mock_cycle_tracker,
        )

        self.mock_intake.assert_called_once()
        args, kwargs = self.mock_intake.call_args
        self.assertIn(self.session_id, str(args) + str(kwargs))
        self.assertIn("블로그 후속 SNS 게시 요청 접수", str(args) + str(kwargs))

    def test_state_transitions_follow_risp_lifecycle(self):
        """Must go through the correct RISP states."""
        run_pipeline(
            source_url=self.source_url,
            session_id=self.session_id,
            intake_func=self.mock_intake,
            signaler=self.mock_signaler,
            state_manager=self.mock_state_manager,
            blog_creator=self.mock_blog_creator,
            sns_publisher=self.mock_sns_publisher,
            cycle_tracker=self.mock_cycle_tracker,
            auto_sns=True,
        )

        # Check key state updates were attempted
        update_calls = [c[0][1] for c in self.mock_state_manager.update_status.call_args_list]
        self.assertIn("RECEIVED", str(update_calls))
        self.assertIn("BLOG_PUBLISHED", str(update_calls))
        self.assertIn("SNS_PUBLISHING_STARTED", str(update_calls))
        self.assertTrue(
            any("COMPLETED" in str(c) or "SNS_PARTIAL_FAILURE" in str(c) for c in update_calls)
        )

    def test_signaling_happens_at_every_major_stage(self):
        """No silent stages. Every important step must produce a signal."""
        run_pipeline(
            source_url=self.source_url,
            session_id=self.session_id,
            intake_func=self.mock_intake,
            signaler=self.mock_signaler,
            state_manager=self.mock_state_manager,
            blog_creator=self.mock_blog_creator,
            sns_publisher=self.mock_sns_publisher,
            cycle_tracker=self.mock_cycle_tracker,
            auto_sns=True,
        )

        signals = [str(c) for c in self.mock_signaler.call_args_list]

        self.assertTrue(any("요청 접수 완료" in s for s in signals), "Missing intake signal")
        self.assertTrue(any("블로그 발행 확인" in s for s in signals), "Missing blog check signal")
        self.assertTrue(any("블로그 발행 완료" in s for s in signals), "Missing blog published signal")
        self.assertTrue(any("SNS 자동 게시" in s for s in signals), "Missing SNS start signal")
        self.assertTrue(any("후속 SNS 게시 완료" in s for s in signals), "Missing final success signal")

    def test_auto_sns_true_triggers_real_publishing_path(self):
        """When auto_sns=True (default for the new flow), it must attempt real SNS publish."""
        run_pipeline(
            source_url=self.source_url,
            session_id=self.session_id,
            intake_func=self.mock_intake,
            signaler=self.mock_signaler,
            state_manager=self.mock_state_manager,
            blog_creator=self.mock_blog_creator,
            sns_publisher=self.mock_sns_publisher,
            cycle_tracker=self.mock_cycle_tracker,
            auto_sns=True,
        )

        self.mock_sns_publisher.assert_called()

    def test_failure_in_blog_stage_is_signaled_and_state_marked_failed(self):
        """If blog creation fails, we must signal clearly and mark state FAILED."""
        self.mock_blog_creator.return_value = {"success": False, "error": "Draft validation failed"}

        result = run_pipeline(
            source_url=self.source_url,
            session_id=self.session_id,
            intake_func=self.mock_intake,
            signaler=self.mock_signaler,
            state_manager=self.mock_state_manager,
            blog_creator=self.mock_blog_creator,
            sns_publisher=self.mock_sns_publisher,
            cycle_tracker=self.mock_cycle_tracker,
        )

        self.assertFalse(result["success"])
        signals = [str(c) for c in self.mock_signaler.call_args_list]
        self.assertTrue(any("블로그 작성 실패" in s for s in signals))

        # Should have tried to mark failed
        fail_calls = self.mock_state_manager.mark_failed.call_args_list
        self.assertTrue(len(fail_calls) > 0 or any("FAILED" in str(c) for c in self.mock_state_manager.update_status.call_args_list))

    def test_sns_failure_still_returns_useful_next_action_style_info(self):
        """Even on SNS failure, the result should contain actionable information."""
        self.mock_sns_publisher.return_value = {
            "success": False,
            "results": {"threads": {"success": False, "error": "rate limit 368"}}
        }

        result = run_pipeline(
            source_url=self.source_url,
            session_id=self.session_id,
            intake_func=self.mock_intake,
            signaler=self.mock_signaler,
            state_manager=self.mock_state_manager,
            blog_creator=self.mock_blog_creator,
            sns_publisher=self.mock_sns_publisher,
            cycle_tracker=self.mock_cycle_tracker,
            auto_sns=True,
        )

        self.assertFalse(result.get("success"))
        # The pipeline should surface error info for the caller / signaler
        self.assertIn("sns_result", result)

    def test_auto_publish_blocks_without_approval_log(self):
        """Real SNS publishing must not invent a temporary empty-media approval log."""
        result = auto_publish_sns(
            blog_url="https://example.com/post/",
            session_id="test-no-approval",
            approval_log_path=None,
        )

        self.assertFalse(result["success"])
        self.assertTrue(result.get("blocked"))
        self.assertIn("approval log", result["error"])


if __name__ == "__main__":
    unittest.main()
