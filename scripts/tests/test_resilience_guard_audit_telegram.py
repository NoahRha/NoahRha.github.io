#!/usr/bin/env python3
"""
Track-A 2026-06-07 self-test: blog_workflow_guard audit 실패 시 텔레그램
호출이 트리거되는지 검증 + 3-tier fallback 체인 단위 테스트.

검증 항목:
1. cmd_audit이 실패 시 _send_telegram_alert을 호출 (mock)
2. set_blocked_reason이 workflow state에 blocked_reason 필드 추가
3. is_stale이 30분 임계값을 정확히 계산
4. _send_via_mavis / _send_via_openclaw / _send_direct_http fallback 체인
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

WORKSPACE = Path("/Users/noah/.openclaw/workspace-blogger")
sys.path.insert(0, str(WORKSPACE))
sys.path.insert(0, str(WORKSPACE / "scripts"))

import importlib.util  # noqa: E402

GUARD_PATH = WORKSPACE / "scripts" / "blog_workflow_guard.py"
spec = importlib.util.spec_from_file_location("blog_workflow_guard", GUARD_PATH)
bwg = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bwg)

from risp.signaling import session_signaler  # noqa: E402


class TestResilienceGuardAuditTelegram(unittest.TestCase):
    """blog_workflow_guard의 audit → telegram 알림 path 검증."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmp.name)
        # STATE_DIR을 임시로 교체
        self._orig_state_dir = bwg.STATE_DIR
        bwg.STATE_DIR = self.tmp_path / "workflow-runs"
        bwg.STATE_DIR.mkdir(parents=True, exist_ok=True)
        # 디스크 telegram 알림을 차단 (테스트 중 발송 방지)
        self._orig_telegram_func = bwg._send_telegram_alert
        bwg._send_telegram_alert = MagicMock(return_value=True)

    def tearDown(self):
        bwg.STATE_DIR = self._orig_state_dir
        bwg._send_telegram_alert = self._orig_telegram_func
        self.tmp.cleanup()

    def _make_state(self, slug: str, **extra) -> Path:
        state = {
            "schema_version": "1.0",
            "slug": slug,
            "title": "Test",
            "source_url": "https://example.com/article",
            "style": "hand-drawing",
            "mode": "blog-sns",
            "status": "RECEIVED",
            "created_at": "2026-06-07T10:00:00+09:00",
            "updated_at": "2026-06-07T10:00:00+09:00",
            "paths": {
                "post": "content/posts/test.md",
                "sns": "content/social/test-sns.md",
                "image_dir": "static/images/test",
            },
            "review": {
                "claude": "pending",
                "gpt_fallback": "pending",
                "minimax": "pending",
                "minimax_revisions": 0,
                "humanize_korean": "pending",
                "poetry_rhythm": "pending",
            },
            "notes": [],
        }
        state.update(extra)
        path = bwg.state_path_for_slug(slug)
        path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return path

    def test_audit_failure_sends_telegram(self):
        """audit 실패 시 _send_telegram_alert가 호출되어야 함."""
        slug = "audit-fail-tg"
        self._make_state(slug)

        # build args namespace mimicking cmd_audit CLI
        args = MagicMock()
        args.slug = slug
        args.stage = "prebuild"  # source URL + post 있어야 통과하는 단계
        args.mode = "blog-sns"
        args.source_url = None
        args.post = None
        args.sns = None
        args.image_dir = None
        args.image_plan = None
        args.require_build = False
        args.require_git_visibility = False
        args.allow_sns_without_source = False

        # post 파일을 일부러 만들지 않아 audit이 fail하도록 한다.
        rc = bwg.cmd_audit(args)
        self.assertEqual(rc, 1, "audit should fail when post file is missing")

        # 텔레그램 알림이 호출되었는지 검증
        bwg._send_telegram_alert.assert_called_once()
        call_args = bwg._send_telegram_alert.call_args
        # (slug, message, level="error") 형태로 호출됨 (level은 keyword)
        self.assertEqual(call_args[0][0], slug)
        self.assertIn("audit", call_args[0][1].lower())
        # level 인자 (positional or keyword)
        if len(call_args[0]) >= 3:
            self.assertEqual(call_args[0][2], "error")
        else:
            self.assertEqual(call_args[1].get("level"), "error")

    def test_audit_failure_writes_blocked_reason(self):
        """audit 실패 시 state 파일에 blocked_reason 필드가 기록되어야 함."""
        slug = "audit-blocked-reason"
        self._make_state(slug)

        args = MagicMock()
        args.slug = slug
        args.stage = "prebuild"
        args.mode = "blog-sns"
        args.source_url = None
        args.post = None
        args.sns = None
        args.image_dir = None
        args.image_plan = None
        args.require_build = False
        args.require_git_visibility = False
        args.allow_sns_without_source = False

        rc = bwg.cmd_audit(args)
        self.assertEqual(rc, 1)

        # state 파일 다시 읽어서 blocked_reason 확인
        state = json.loads(bwg.state_path_for_slug(slug).read_text(encoding="utf-8"))
        self.assertIn("blocked_reason", state)
        self.assertIn("audit", state["blocked_reason"].lower())
        self.assertEqual(state["status"], "BLOCKED")

    def test_set_blocked_reason_helper(self):
        """set_blocked_reason helper가 state에 직접 기록하는지 검증."""
        slug = "set-blocked-test"
        self._make_state(slug)
        bwg.set_blocked_reason(slug, "test reason 123")
        state = json.loads(bwg.state_path_for_slug(slug).read_text(encoding="utf-8"))
        self.assertEqual(state["blocked_reason"], "test reason 123")
        self.assertEqual(state["status"], "BLOCKED")
        self.assertTrue(any("test reason 123" in n["text"] for n in state.get("notes", [])))

    def test_is_stale_30_minutes(self):
        """updated_at 30분 이상 지난 state는 stale로 판정."""
        from datetime import datetime, timezone, timedelta

        KST = timezone(timedelta(hours=9))
        slug = "stale-test"
        # 1시간 전
        old_time = (datetime.now(KST) - timedelta(hours=1)).isoformat(timespec="seconds")
        self._make_state(slug, updated_at=old_time)
        self.assertTrue(bwg.is_stale(slug, threshold_minutes=30))

        # 1분 전 (stale 아님)
        fresh_time = (datetime.now(KST) - timedelta(minutes=1)).isoformat(timespec="seconds")
        self._make_state(slug, updated_at=fresh_time)
        self.assertFalse(bwg.is_stale(slug, threshold_minutes=30))

    def test_check_stale_command(self):
        """check-stale CLI가 30분 이상 미갱신 state를 찾아 BLOCKED 처리."""
        from datetime import datetime, timezone, timedelta

        KST = timezone(timedelta(hours=9))
        slug_old = "stale-old"
        slug_fresh = "stale-fresh"

        old_time = (datetime.now(KST) - timedelta(hours=2)).isoformat(timespec="seconds")
        fresh_time = (datetime.now(KST) - timedelta(minutes=5)).isoformat(timespec="seconds")
        self._make_state(slug_old, updated_at=old_time)
        self._make_state(slug_fresh, updated_at=fresh_time)

        # Run the subcommand directly
        args = MagicMock()
        args.slug = None
        args.threshold_minutes = 30
        args.all = True
        bwg._send_telegram_alert.reset_mock()
        rc = bwg.cmd_check_stale(args)

        # stale 하나만 발견
        self.assertEqual(rc, 1)
        # 텔레그램 알림 1회 (stale-old만)
        self.assertEqual(bwg._send_telegram_alert.call_count, 1)
        # state 파일에 blocked_reason 기록
        state_old = json.loads(bwg.state_path_for_slug(slug_old).read_text(encoding="utf-8"))
        self.assertIn("blocked_reason", state_old)
        self.assertIn("stale", state_old["blocked_reason"])

    def test_mark_blocked_command(self):
        """mark-blocked CLI가 blocked_reason 기록 + 텔레그램 알림."""
        slug = "mark-blocked-test"
        self._make_state(slug)
        args = MagicMock()
        args.slug = slug
        args.reason = "manual block from test"
        bwg._send_telegram_alert.reset_mock()
        rc = bwg.cmd_mark_blocked(args)
        self.assertEqual(rc, 0)
        bwg._send_telegram_alert.assert_called_once()
        state = json.loads(bwg.state_path_for_slug(slug).read_text(encoding="utf-8"))
        self.assertEqual(state["blocked_reason"], "manual block from test")
        self.assertEqual(state["status"], "BLOCKED")


class TestResilienceTelegramFallbackChain(unittest.TestCase):
    """_send_telegram의 3-tier fallback 체인 검증 (openclaw → http → mavis)."""

    def test_falls_through_to_direct_http_when_openclaw_fails(self):
        """openclaw CLI 실패 시 direct HTTP로 폴백."""
        with patch.object(session_signaler, "_send_via_openclaw", return_value=(False, "openclaw down")):
            with patch.object(
                session_signaler,
                "_send_direct_http",
                return_value=(True, "direct http ok"),
            ) as mock_http:
                with patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN_BLOGGER": "fake-token"}):
                    with patch.object(session_signaler.shutil, "which", return_value=None):
                        # Should not raise — direct http succeeded
                        session_signaler._send_telegram("hi", "telegram:554534300")
                        mock_http.assert_called_once()

    def test_falls_through_to_mavis_when_both_openclaw_and_http_fail(self):
        """openclaw + http 둘 다 실패 시 mavis로 폴백."""
        with patch.object(session_signaler, "_send_via_openclaw", return_value=(False, "openclaw down")):
            with patch.object(
                session_signaler,
                "_send_direct_http",
                return_value=(False, "DNS error"),
            ):
                with patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN_BLOGGER": "fake-token"}):
                    with patch.object(session_signaler, "_send_via_mavis", return_value=(True, "mavis ok")) as mock_mavis:
                        session_signaler._send_telegram("hi", "telegram:554534300")
                        mock_mavis.assert_called_once()

    def test_raises_when_all_three_tiers_fail(self):
        """3-tier 모두 실패 시 RuntimeError 발생 (호출자가 fail log에 기록)."""
        with patch.object(session_signaler, "_send_via_openclaw", return_value=(False, "openclaw down")):
            with patch.object(
                session_signaler,
                "_send_direct_http",
                return_value=(False, "DNS error"),
            ):
                with patch.object(session_signaler, "_send_via_mavis", return_value=(False, "mavis also down")):
                    with patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN_BLOGGER": "fake-token"}):
                        with self.assertRaises(RuntimeError) as ctx:
                            session_signaler._send_telegram("hi", "telegram:554534300")
                        msg = str(ctx.exception)
                        self.assertIn("3/3 tiers", msg)
                        self.assertIn("수동 재시도", msg)

    def test_silent_when_no_chat_id(self):
        """chat_id가 없으면 silent (log-only)."""
        with patch.dict(os.environ, {}, clear=True):
            # Should not raise
            session_signaler._send_telegram("hi", "no-telegram-prefix")

    def test_openclaw_succeeds_no_fallback(self):
        """openclaw 성공 시 http/mavis는 호출되지 않음."""
        with patch.object(
            session_signaler, "_send_via_openclaw", return_value=(True, "openclaw ok")
        ) as mock_openclaw:
            with patch.object(
                session_signaler, "_send_direct_http"
            ) as mock_http:
                with patch.object(session_signaler, "_send_via_mavis") as mock_mavis:
                    session_signaler._send_telegram("hi", "telegram:554534300")
                    mock_openclaw.assert_called_once()
                    mock_http.assert_not_called()
                    mock_mavis.assert_not_called()


if __name__ == "__main__":
    unittest.main(verbosity=2)
