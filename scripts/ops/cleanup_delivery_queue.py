#!/usr/bin/env python3
"""
delivery-queue 자동 청소 스크립트 (Track-A 2026-06-07).

`~/.openclaw/delivery-queue/failed/`에 누적된 실패 메시지를 분류·처리한다.

동작 규칙:
1. **24시간 경과**: 영구 실패로 간주하고 mavis-trash로 이동 (복구 가능).
2. **일시 실패 (transient)**: 502 / Network / DNS / timeout류.
   - retryCount가 0이면 inbox(또는 별도 retry 디렉터리)로 1회 재시도.
   - retryCount가 이미 ≥1이면 영구 실패로 간주하고 텔레그램 알림 후 로그.
3. **영구 실패 (permanent)**: 4xx (auth, validation, message thread not found 등).
   - 즉시 텔레그램 알림 + 로그.
   - 24시간 경과 후 자동 trash 대상.

cron 등록 가이드 (이 스크립트는 cron을 직접 건드리지 않음 — 가이드만 문서화):
```
# 매일 03:30 KST, 1회 실행
30 3 * * * /opt/homebrew/bin/python3 /Users/noah/.openclaw/workspace-blogger/scripts/ops/cleanup_delivery_queue.py --quiet >> /Users/noah/.openclaw/workspace-blogger/data/cleanup_delivery_queue.log 2>&1
```

옵션:
  --dry-run        실제 trash / 재시도 없이 시뮬레이션만.
  --threshold-hours N  24시간 대신 다른 임계값 (default 24).
  --no-retry       자동 재시도 비활성 (trash + 알림만).
  --quiet          stdout 요약만 stderr 로그 억제.
  --json           결과를 JSON 한 줄로 출력.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any


KST = timezone(timedelta(hours=9))
DEFAULT_FAILED_DIR = Path.home() / ".openclaw" / "delivery-queue" / "failed"
DEFAULT_INBOX_DIR = Path.home() / ".openclaw" / "delivery-queue" / "inbox"
DEFAULT_LOG_PATH = Path.home() / ".openclaw" / "workspace-blogger" / "data" / "cleanup_delivery_queue.log"
TELEGRAM_LOG = Path.home() / ".openclaw" / "workspace-blogger" / "data" / "risp_telegram_failures.log"

# 에러 패턴 분류 (정규식). 더 위쪽에 매칭될수록 우선.
TRANSIENT_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"502[:\s]Bad Gateway", re.IGNORECASE),
    re.compile(r"5\d\d[:\s]"),
    re.compile(r"Network request.*failed", re.IGNORECASE),
    re.compile(r"timeout|timed out|ETIMEDOUT|ECONNRESET|ECONNREFUSED", re.IGNORECASE),
    re.compile(r"nodename nor servname|getaddrinfo|DNS|Name or service not known", re.IGNORECASE),
    re.compile(r"getaddrinfo ENOTFOUND|ENETUNREACH|EAI_AGAIN", re.IGNORECASE),
    re.compile(r"connection (reset|closed|failed|refused)", re.IGNORECASE),
]
PERMANENT_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"4\d\d[:\s]"),
    re.compile(r"Bad Request|Unauthorized|Forbidden|Not Found", re.IGNORECASE),
    re.compile(r"chat not found|message thread not found|bot was blocked", re.IGNORECASE),
    re.compile(r"invalid token|bot_token", re.IGNORECASE),
]


def classify_error(error: str) -> str:
    """에러 문자열을 transient / permanent / unknown으로 분류한다."""
    if not error:
        return "unknown"
    for pat in PERMANENT_PATTERNS:
        if pat.search(error):
            return "permanent"
    for pat in TRANSIENT_PATTERNS:
        if pat.search(error):
            return "transient"
    return "unknown"


def age_hours(enqueued_at_ms: int, now_ms: int | None = None) -> float:
    now = now_ms if now_ms is not None else int(time.time() * 1000)
    return (now - enqueued_at_ms) / 1000.0 / 3600.0


def safe_mavis_trash(path: Path, dry_run: bool = False) -> tuple[bool, str]:
    """
    mavis-trash CLI를 우선 사용 (OS 휴지통으로 이동, 복구 가능). 없으면
    python pathlib.Path.unlink로 폴더 trash.
    """
    if dry_run:
        return True, f"dry-run: would trash {path}"
    bin_path = shutil.which("mavis-trash")
    if bin_path:
        try:
            proc = subprocess.run(
                [bin_path, str(path)],
                check=False,
                capture_output=True,
                text=True,
                timeout=10,
            )
            if proc.returncode == 0:
                return True, f"mavis-trash ok: {proc.stdout.strip()}"
            return False, f"mavis-trash failed: {proc.stderr.strip()}"
        except Exception as e:
            return False, f"mavis-trash exception: {e}"
    # fallback: 명시적으로 Path.unlink. cron 운영에서는 mavis-trash가
    # 항상 설치되어 있어야 한다.
    try:
        path.unlink()
        return True, f"unlinked {path} (no mavis-trash CLI; consider installing it)"
    except Exception as e:
        return False, f"unlink failed: {e}"


def safe_move_to_inbox(path: Path, inbox: Path, dry_run: bool = False) -> tuple[bool, str]:
    """
    inbox 디렉터리로 이동 (재시도 큐). mavis-trash는 사용하지 않음 (복구용).
    inbox/<id>.json 형태로 보존.
    """
    if dry_run:
        return True, f"dry-run: would move {path} -> {inbox / path.name}"
    inbox.mkdir(parents=True, exist_ok=True)
    dest = inbox / path.name
    if dest.exists():
        # 충돌 회피: timestamp suffix
        ts = int(time.time())
        dest = inbox / f"{path.stem}-{ts}{path.suffix}"
    try:
        shutil.move(str(path), str(dest))
        return True, f"moved {path} -> {dest}"
    except Exception as e:
        return False, f"move failed: {e}"


def send_telegram_alert(payload_text: str, level: str = "error") -> bool:
    """
    RISP session_signaler의 3-tier fallback (openclaw → http → mavis)을
    사용해서 텔레그램으로 알림.
    """
    try:
        # sys.path 보정: workspace-blogger가 PYTHONPATH에 없을 수 있다.
        workspace_root = Path(__file__).resolve().parents[2]
        if str(workspace_root) not in sys.path:
            sys.path.insert(0, str(workspace_root))
        from risp.signaling.session_signaler import send_message

        # session_id 결정: 환경변수 또는 기본 owner chat.
        chat_id = (
            os.environ.get("RISP_TELEGRAM_CHAT_ID")
            or os.environ.get("TELEGRAM_OWNER_CHAT_ID")
            or "554534300"
        )
        thread_id = os.environ.get("RISP_TELEGRAM_THREAD_ID")
        session_id = f"telegram:{chat_id}"
        if thread_id:
            session_id += f":thread:{thread_id}"

        send_message(session_id, payload_text, level=level)
        return True
    except Exception as e:
        # 텔레그램 발송 실패는 절대 cleanup 자체를 막아선 안 된다.
        # stderr로만 남기고 다음 항목으로 진행.
        print(f"[TELEGRAM-ALERT-FAILED] {e}", file=sys.stderr)
        return False


def summarize_message(entry: dict[str, Any]) -> str:
    """사람이 읽을 한 줄 요약."""
    rid = entry.get("id", "(no-id)")
    to = entry.get("to", "(unknown)")
    err = (entry.get("lastError") or "").strip()[:200]
    text = ""
    payloads = entry.get("payloads") or []
    if payloads and isinstance(payloads[0], dict):
        text = (payloads[0].get("text") or "").strip().replace("\n", " ")[:120]
    return f"id={rid} to={to} err={err!r} text={text!r}"


def process_entry(
    path: Path,
    *,
    threshold_hours: float,
    inbox: Path,
    log_path: Path,
    dry_run: bool,
    no_retry: bool,
    quiet: bool,
) -> dict[str, Any]:
    """
    단일 failed entry를 처리. 반환값은 요약 dict.
    """
    try:
        entry = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        return {"file": str(path), "action": "skipped", "reason": f"invalid JSON: {e}"}

    error = entry.get("lastError") or ""
    classification = classify_error(error)
    enqueued_at = int(entry.get("enqueuedAt") or 0)
    hours = age_hours(enqueued_at) if enqueued_at else 0.0
    retry_count = int(entry.get("retryCount") or 0)

    result: dict[str, Any] = {
        "file": str(path),
        "id": entry.get("id"),
        "classification": classification,
        "age_hours": round(hours, 2),
        "retryCount": retry_count,
        "action": None,
        "detail": None,
    }

    # Rule 1: 24시간 경과 → 자동 trash.
    if hours >= threshold_hours:
        ok, detail = safe_mavis_trash(path, dry_run=dry_run)
        result["action"] = "trashed" if ok else "trash_failed"
        result["detail"] = detail
        return result

    # Rule 2: permanent (4xx) → 텔레그램 알림 + log. trash는 안 함 (24시간 대기).
    if classification == "permanent":
        msg = (
            f"🛑 [delivery-queue] 영구 실패 감지 (4xx/validation)\n"
            f"  • {summarize_message(entry)}\n"
            f"  • {threshold_hours - hours:.1f}시간 후 자동 trash 예정"
        )
        if not quiet:
            print(msg, file=sys.stderr)
        send_telegram_alert(msg, level="error")
        result["action"] = "alerted_permanent"
        return result

    # Rule 3: transient → retryCount 0이면 1회 inbox로 이동 (재시도 큐).
    if classification == "transient" and retry_count < 1 and not no_retry:
        ok, detail = safe_move_to_inbox(path, inbox, dry_run=dry_run)
        result["action"] = "retried_to_inbox" if ok else "retry_move_failed"
        result["detail"] = detail
        if ok:
            # entry의 retryCount를 1로 갱신해서 다음 cleanup이 1회로 인식.
            try:
                entry["retryCount"] = retry_count + 1
                entry["lastRetryAt"] = int(time.time() * 1000)
                if not dry_run:
                    # inbox에 있는 파일을 갱신
                    moved_path = inbox / path.name
                    if moved_path.exists():
                        moved_path.write_text(
                            json.dumps(entry, ensure_ascii=False, indent=2) + "\n",
                            encoding="utf-8",
                        )
            except Exception as e:
                result["detail"] = f"{detail} (retryCount update failed: {e})"
        return result

    # Rule 4: transient이지만 retryCount ≥ 1 → 영구 실패로 격상 + 알림.
    if classification == "transient" and retry_count >= 1:
        msg = (
            f"⚠️ [delivery-queue] 일시 실패 1회 재시도 후에도 실패\n"
            f"  • {summarize_message(entry)}\n"
            f"  • {threshold_hours - hours:.1f}시간 후 자동 trash 예정"
        )
        if not quiet:
            print(msg, file=sys.stderr)
        send_telegram_alert(msg, level="warn")
        result["action"] = "alerted_retry_exhausted"
        return result

    # Rule 5: unknown → 일단 보류, 24시간 후 trash.
    result["action"] = "kept_unknown"
    return result


def cmd_cleanup(args: argparse.Namespace) -> int:
    failed_dir: Path = args.failed_dir
    inbox: Path = args.inbox
    threshold = args.threshold_hours
    dry_run = args.dry_run
    no_retry = args.no_retry
    quiet = args.quiet

    if not failed_dir.exists():
        print(f"[ERROR] failed dir not found: {failed_dir}", file=sys.stderr)
        return 2

    log_path = args.log_path
    log_path.parent.mkdir(parents=True, exist_ok=True)

    summary: list[dict[str, Any]] = []
    counts: dict[str, int] = {
        "total": 0,
        "trashed": 0,
        "retried_to_inbox": 0,
        "alerted_permanent": 0,
        "alerted_retry_exhausted": 0,
        "kept_unknown": 0,
        "skipped": 0,
        "trash_failed": 0,
        "retry_move_failed": 0,
    }

    for path in sorted(failed_dir.glob("*.json")):
        counts["total"] += 1
        result = process_entry(
            path,
            threshold_hours=threshold,
            inbox=inbox,
            log_path=log_path,
            dry_run=dry_run,
            no_retry=no_retry,
            quiet=quiet,
        )
        action = result.get("action") or "skipped"
        counts[action] = counts.get(action, 0) + 1
        summary.append(result)

    # 로그 파일에 한 줄 JSON append (사후 분석용).
    if not dry_run:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(
                json.dumps(
                    {
                        "timestamp": datetime.now(KST).isoformat(timespec="seconds"),
                        "counts": counts,
                        "entries": summary,
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )

    if args.json:
        print(json.dumps({"counts": counts, "entries": summary}, ensure_ascii=False))
    else:
        print(json.dumps({"counts": counts}, ensure_ascii=False, indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Track-A 2026-06-07: delivery-queue/failed 자동 청소"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    cleanup = sub.add_parser("cleanup", help="기본 청소 실행 (한 번)")
    cleanup.add_argument("--failed-dir", type=Path, default=DEFAULT_FAILED_DIR)
    cleanup.add_argument("--inbox", type=Path, default=DEFAULT_INBOX_DIR)
    cleanup.add_argument("--log-path", type=Path, default=DEFAULT_LOG_PATH)
    cleanup.add_argument(
        "--threshold-hours", type=float, default=24.0,
        help="이 시간 이상 지난 failed 항목은 자동 trash (default 24)",
    )
    cleanup.add_argument("--dry-run", action="store_true", help="trash / 이동 없이 결과만")
    cleanup.add_argument("--no-retry", action="store_true", help="transient 자동 재시도 비활성")
    cleanup.add_argument("--quiet", action="store_true", help="stderr 알림 출력 억제")
    cleanup.add_argument("--json", action="store_true", help="결과를 JSON 한 줄로 출력")
    cleanup.set_defaults(func=cmd_cleanup)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
