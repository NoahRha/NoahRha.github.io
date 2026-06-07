#!/usr/bin/env python3
"""
Track-A 2026-06-07 self-test: delivery-queue cleanup 동작 검증.

검증 항목:
1. 24시간 지난 failed 항목만 trash
2. 일시 실패 (transient, retryCount=0)는 inbox로 이동
3. 영구 실패 (4xx)는 알림 + 24시간 후 trash
4. classify_error가 transient/permanent/unknown을 올바르게 분류
5. mavis-trash 미설치 시 fallback (unlink)
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

WORKSPACE = Path("/Users/noah/.openclaw/workspace-blogger")
sys.path.insert(0, str(WORKSPACE))

import importlib.util  # noqa: E402

CLEANUP_PATH = WORKSPACE / "scripts" / "ops" / "cleanup_delivery_queue.py"
spec = importlib.util.spec_from_file_location("cleanup_delivery_queue", CLEANUP_PATH)
cdq = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cdq)


def _make_failed_entry(
    error: str,
    *,
    age_hours: float = 1.0,
    retry_count: int = 0,
    id_suffix: str = "test",
) -> dict:
    return {
        "id": f"cdq-test-{id_suffix}",
        "enqueuedAt": int((time.time() - age_hours * 3600) * 1000),
        "channel": "telegram",
        "to": "telegram:554534300",
        "accountId": "blogger",
        "payloads": [{"text": f"test message {id_suffix}"}],
        "retryCount": retry_count,
        "lastError": error,
    }


class TestResilienceDeliveryCleanup(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.failed_dir = Path(self.tmp.name) / "failed"
        self.inbox_dir = Path(self.tmp.name) / "inbox"
        self.failed_dir.mkdir(parents=True, exist_ok=True)
        self.inbox_dir.mkdir(parents=True, exist_ok=True)
        self.log_path = Path(self.tmp.name) / "cleanup.log"

    def tearDown(self):
        self.tmp.cleanup()

    def _write_entry(self, entry: dict, name: str | None = None) -> Path:
        name = name or f"{entry['id']}.json"
        path = self.failed_dir / name
        path.write_text(json.dumps(entry, ensure_ascii=False), encoding="utf-8")
        return path

    def test_classify_error_502_is_transient(self):
        self.assertEqual(cdq.classify_error("502: Bad Gateway"), "transient")
        self.assertEqual(cdq.classify_error("Network request failed"), "transient")
        self.assertEqual(cdq.classify_error("ETIMEDOUT"), "transient")
        self.assertEqual(cdq.classify_error("getaddrinfo ENOTFOUND"), "transient")

    def test_classify_error_400_is_permanent(self):
        self.assertEqual(cdq.classify_error("400: Bad Request"), "permanent")
        self.assertEqual(cdq.classify_error("Unauthorized"), "permanent")
        self.assertEqual(cdq.classify_error("message thread not found"), "permanent")
        self.assertEqual(cdq.classify_error("bot was blocked"), "permanent")

    def test_classify_error_unknown(self):
        self.assertEqual(cdq.classify_error(""), "unknown")
        self.assertEqual(cdq.classify_error("something weird happened"), "unknown")

    def test_permanent_takes_priority_over_transient(self):
        # 502 + 400 혼합이면 4xx가 우선
        self.assertEqual(cdq.classify_error("502 + 400 Bad Request"), "permanent")

    def test_24h_old_entry_is_trashed(self):
        """25시간 된 failed는 mavis-trash로 이동."""
        entry = _make_failed_entry("400: Bad Request", age_hours=25)
        path = self._write_entry(entry)

        with patch.object(cdq, "safe_mavis_trash", return_value=(True, "ok")) as mock_trash:
            result = cdq.process_entry(
                path,
                threshold_hours=24.0,
                inbox=self.inbox_dir,
                log_path=self.log_path,
                dry_run=False,
                no_retry=False,
                quiet=True,
            )
        self.assertEqual(result["action"], "trashed")
        mock_trash.assert_called_once()

    def test_23h_old_permanent_is_alerted_not_trashed(self):
        """23시간 4xx 에러는 알림만, 24시간 후 trash 대기."""
        entry = _make_failed_entry("400: Bad Request", age_hours=23)
        path = self._write_entry(entry)
        with patch.object(cdq, "send_telegram_alert", return_value=True) as mock_tg:
            with patch.object(cdq, "safe_mavis_trash") as mock_trash:
                result = cdq.process_entry(
                    path,
                    threshold_hours=24.0,
                    inbox=self.inbox_dir,
                    log_path=self.log_path,
                    dry_run=False,
                    no_retry=False,
                    quiet=True,
                )
        self.assertEqual(result["action"], "alerted_permanent")
        mock_tg.assert_called_once()
        mock_trash.assert_not_called()  # 24시간 지나기 전엔 trash 안 함

    def test_23h_old_transient_zero_retry_moves_to_inbox(self):
        """23시간 transient, retryCount=0 → inbox로 1회 재시도."""
        entry = _make_failed_entry("502: Bad Gateway", age_hours=23, retry_count=0)
        path = self._write_entry(entry)
        with patch.object(cdq, "send_telegram_alert") as mock_tg:
            result = cdq.process_entry(
                path,
                threshold_hours=24.0,
                inbox=self.inbox_dir,
                log_path=self.log_path,
                dry_run=False,
                no_retry=False,
                quiet=True,
            )
        self.assertEqual(result["action"], "retried_to_inbox")
        # inbox에 파일이 실제로 있어야 함
        inbox_files = list(self.inbox_dir.glob("*.json"))
        self.assertEqual(len(inbox_files), 1)
        # retryCount가 1로 갱신
        moved = json.loads(inbox_files[0].read_text(encoding="utf-8"))
        self.assertEqual(moved["retryCount"], 1)
        # 텔레그램 알림은 발송 안 됨 (정상 재시도)
        mock_tg.assert_not_called()

    def test_23h_old_transient_one_retry_alerts(self):
        """23시간 transient, retryCount=1 → 1회 재시도 소진 → 알림."""
        entry = _make_failed_entry("502: Bad Gateway", age_hours=23, retry_count=1)
        path = self._write_entry(entry)
        with patch.object(cdq, "send_telegram_alert", return_value=True) as mock_tg:
            result = cdq.process_entry(
                path,
                threshold_hours=24.0,
                inbox=self.inbox_dir,
                log_path=self.log_path,
                dry_run=False,
                no_retry=False,
                quiet=True,
            )
        self.assertEqual(result["action"], "alerted_retry_exhausted")
        mock_tg.assert_called_once()

    def test_dry_run_does_not_trash(self):
        """--dry-run은 실제 trash 안 함."""
        entry = _make_failed_entry("400: Bad Request", age_hours=25)
        path = self._write_entry(entry)
        result = cdq.process_entry(
            path,
            threshold_hours=24.0,
            inbox=self.inbox_dir,
            log_path=self.log_path,
            dry_run=True,
            no_retry=False,
            quiet=True,
        )
        self.assertEqual(result["action"], "trashed")
        self.assertIn("dry-run", result["detail"])
        # 파일이 실제로는 여전히 존재
        self.assertTrue(path.exists())

    def test_no_retry_blocks_inbox_movement(self):
        """--no-retry 옵션은 transient의 inbox 이동을 막음."""
        entry = _make_failed_entry("502: Bad Gateway", age_hours=1, retry_count=0)
        path = self._write_entry(entry)
        with patch.object(cdq, "send_telegram_alert", return_value=True):
            result = cdq.process_entry(
                path,
                threshold_hours=24.0,
                inbox=self.inbox_dir,
                log_path=self.log_path,
                dry_run=False,
                no_retry=True,  # retry off
                quiet=True,
            )
        # retry off이므로 retryCount=0이라도 inbox로 안 가고, retryCount < 1
        # 조건이 막혀서 "kept_unknown" 또는 "alerted_permanent" 류로 빠진다.
        # 우리 코드는 retry off 시 retry 분기를 안 탐 → kept_unknown.
        self.assertIn(result["action"], {"kept_unknown", "alerted_retry_exhausted"})

    def test_safe_mavis_trash_uses_cli(self):
        """mavis-trash CLI가 있으면 그것을 사용."""
        with tempfile.NamedTemporaryFile(delete=False) as f:
            test_path = Path(f.name)
        try:
            with patch("shutil.which", return_value="/usr/local/bin/mavis-trash"):
                with patch("subprocess.run") as mock_run:
                    mock_run.return_value = MagicMock(returncode=0, stdout="ok", stderr="")
                    ok, detail = cdq.safe_mavis_trash(test_path, dry_run=False)
            self.assertTrue(ok)
            self.assertIn("mavis-trash ok", detail)
            # CLI가 호출되었는지
            mock_run.assert_called_once()
            cmd = mock_run.call_args[0][0]
            self.assertEqual(cmd[0], "/usr/local/bin/mavis-trash")
        finally:
            try:
                test_path.unlink()
            except Exception:
                pass

    def test_safe_mavis_trash_fallback_to_unlink(self):
        """mavis-trash CLI가 없으면 pathlib unlink로 fallback."""
        test_path = Path(self.tmp.name) / "to_trash.json"
        test_path.write_text("{}", encoding="utf-8")
        with patch("shutil.which", return_value=None):
            ok, detail = cdq.safe_mavis_trash(test_path, dry_run=False)
        self.assertTrue(ok)
        self.assertIn("unlinked", detail)
        self.assertFalse(test_path.exists())

    def test_age_hours_calculation(self):
        """age_hours 함수가 ms timestamp를 시간 단위로 변환."""
        now_ms = int(time.time() * 1000)
        one_hour_ago = now_ms - 3600 * 1000
        self.assertAlmostEqual(cdq.age_hours(one_hour_ago, now_ms=now_ms), 1.0, places=2)

    def test_cmd_cleanup_full_flow(self):
        """cmd_cleanup이 mixed entries를 한 번에 처리."""
        # 25h permanent → trash
        e1 = _make_failed_entry("400: Bad Request", age_hours=25, id_suffix="perm-old")
        self._write_entry(e1, name="perm-old.json")
        # 23h transient retry=0 → inbox
        e2 = _make_failed_entry("502: Bad Gateway", age_hours=23, retry_count=0, id_suffix="transient")
        self._write_entry(e2, name="transient.json")
        # 23h permanent → alert only
        e3 = _make_failed_entry("400: Bad Request", age_hours=23, id_suffix="perm-recent")
        self._write_entry(e3, name="perm-recent.json")
        # 1h transient retry=0 → inbox
        e4 = _make_failed_entry("Network request failed", age_hours=1, retry_count=0, id_suffix="network")
        self._write_entry(e4, name="network.json")

        with patch.object(cdq, "send_telegram_alert", return_value=True):
            # mavis-trash CLI 없는 환경 시뮬레이션 → 실제 unlink가 동작
            with patch("shutil.which", return_value=None):
                # failed_dir / inbox / log_path를 monkeypatch
                with patch.object(cdq, "DEFAULT_FAILED_DIR", self.failed_dir):
                    with patch.object(cdq, "DEFAULT_INBOX_DIR", self.inbox_dir):
                        with patch.object(cdq, "DEFAULT_LOG_PATH", self.log_path):
                            args = MagicMock()
                            args.failed_dir = self.failed_dir
                            args.inbox = self.inbox_dir
                            args.log_path = self.log_path
                            args.threshold_hours = 24.0
                            args.dry_run = False
                            args.no_retry = False
                            args.quiet = True
                            args.json = True
                            rc = cdq.cmd_cleanup(args)
        self.assertEqual(rc, 0)
        # 25h permanent (perm-old) → unlink로 trash됨
        self.assertFalse((self.failed_dir / "perm-old.json").exists())
        # 1h transient + 23h transient → inbox로 이동
        inbox_files = sorted([p.name for p in self.inbox_dir.glob("*.json")])
        self.assertIn("transient.json", inbox_files)
        self.assertIn("network.json", inbox_files)
        # 23h permanent는 남아야 함
        self.assertTrue((self.failed_dir / "perm-recent.json").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
