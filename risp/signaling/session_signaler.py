#!/usr/bin/env python3
"""
RISP Session Signaler.

Every RISP signal is written to disk and best-effort delivered to Telegram.
Telegram delivery must never make the publishing workflow fail.

Delivery path (Track-A 2026-06-07 update):
- Primary (1): `openclaw message send` CLI, which talks to the local OpenClaw
  gateway on 127.0.0.1:18789. The gateway owns all Telegram bot tokens and
  its own connection to api.telegram.org, so the signaler subprocess no
  longer has to perform DNS lookups or hold bot tokens itself.
- Fallback (2): direct HTTP POST to api.telegram.org. Used only when the
  OpenClaw gateway itself is unreachable. DNS failures in the calling
  subprocess are now irrelevant because the gateway does the egress.
- Last-resort (3): `mavis communication send` via the Mavis session router
  (대부분의 워크플로우에서는 gateway가 살아있어 도달하지 않음). 이 경로는
  OpenClaw 텔레그램 발송이 gateway/CLI 양쪽 모두 실패할 때 사용자에게
  가시성을 보장하는 안전망. 메모리 정책: OpenClaw 텔레그램 발송은 기본적으로
  gateway CLI를 사용하므로 이 경로는 fallback 전용으로만 호출한다.
"""

from __future__ import annotations

from pathlib import Path
import json
import os
import shutil
import subprocess
import urllib.parse
import urllib.request
from datetime import datetime


MAX_TELEGRAM_CHARS = 3800
OPENCLAW_BIN = shutil.which("openclaw") or "/Users/noah/.npm-global/bin/openclaw"


def _parse_requester(session_id: str) -> tuple[str | None, int | None]:
    """
    Accept compact requester/session forms when callers provide them:
    - telegram:<chat_id>
    - telegram:<chat_id>:<thread_id>
    - telegram:<chat_id>:thread:<thread_id>
    """
    parts = str(session_id or "").split(":")
    if len(parts) >= 2 and parts[0] == "telegram":
        chat_id = parts[1]
        thread_id = None
        if len(parts) >= 3:
            try:
                thread_id = int(parts[-1])
            except ValueError:
                thread_id = None
        return chat_id, thread_id
    return None, None


def _send_via_openclaw(chat_id: str, thread_id: int | None, message: str) -> tuple[bool, str]:
    """
    Deliver the message via the OpenClaw gateway CLI.

    Returns (ok, detail). The gateway is on loopback so DNS issues in the
    calling subprocess do not affect this path.
    """
    if not os.path.exists(OPENCLAW_BIN):
        return False, f"openclaw binary not found at {OPENCLAW_BIN}"

    cmd = [
        OPENCLAW_BIN,
        "message", "send",
        "--channel", "telegram",
        "--account", "blogger",
        "--target", str(chat_id),
        "--message", message[:MAX_TELEGRAM_CHARS],
    ]
    if thread_id is not None:
        cmd.extend(["--thread-id", str(thread_id)])

    try:
        proc = subprocess.run(
            cmd,
            timeout=30,
            check=False,
            capture_output=True,
            text=True,
        )
    except subprocess.TimeoutExpired:
        return False, "openclaw CLI timeout after 30s"
    except Exception as e:
        return False, f"openclaw CLI invocation failed: {e}"

    if proc.returncode == 0:
        return True, (proc.stdout or "").strip()
    stderr = (proc.stderr or "").strip()
    return False, f"openclaw exit={proc.returncode}: {stderr or proc.stdout!r}"


def _send_direct_http(token: str, chat_id: str, thread_id: int | None, message: str) -> tuple[bool, str]:
    """
    Last-resort direct POST to api.telegram.org. Kept as a safety net for
    the case where the OpenClaw gateway itself is unreachable.
    """
    payload = {
        "chat_id": chat_id,
        "text": message[:MAX_TELEGRAM_CHARS],
        "disable_web_page_preview": "true",
    }
    if thread_id is not None:
        payload["message_thread_id"] = str(thread_id)

    data = urllib.parse.urlencode(payload).encode("utf-8")
    request = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=data,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            response.read()
        return True, "direct http ok"
    except Exception as e:
        return False, str(e)


def _send_via_mavis(chat_id: str, thread_id: int | None, message: str) -> tuple[bool, str]:
    """
    Track-A 2026-06-07: 3rd-tier fallback. Uses `mavis communication send`
    CLI to deliver via the Mavis session router, which in turn hands off
    to the OpenClaw gateway / Telegram through its own connection. This
    works even when the calling subprocess can't talk to the OpenClaw
    gateway directly (e.g. due to socket / loopback issues).

    Returns (ok, detail). `mavis` binary may be missing on minimal hosts,
    in which case the function returns (False, "mavis not found") and
    the caller falls through to the manual-retry guidance.

    Memory policy: OpenClaw Telegram sending is supposed to use the
    OpenClaw gateway CLI (1st/2nd tier). This 3rd tier is **only** an
    emergency safety net to keep RISP workflows visible when both
    normal paths fail. Do not add it as a primary path.
    """
    mavis_bin = shutil.which("mavis")
    if not mavis_bin:
        return False, "mavis CLI not found in PATH"

    target = f"telegram:{chat_id}"
    cmd = [
        mavis_bin,
        "communication", "send",
        "--to", target,
        "--command", "prompt",
        "--content", message[:MAX_TELEGRAM_CHARS],
    ]
    try:
        proc = subprocess.run(
            cmd,
            timeout=20,
            check=False,
            capture_output=True,
            text=True,
        )
    except subprocess.TimeoutExpired:
        return False, "mavis CLI timeout after 20s"
    except Exception as e:
        return False, f"mavis CLI invocation failed: {e}"

    if proc.returncode == 0:
        return True, (proc.stdout or "").strip()
    stderr = (proc.stderr or "").strip()
    return False, f"mavis exit={proc.returncode}: {stderr or proc.stdout!r}"


def _send_telegram(message: str, session_id: str):
    """Best-effort Telegram delivery with 3-tier fallback chain.

    Tier 1: openclaw CLI → OpenClaw gateway → Telegram.
    Tier 2: direct HTTP POST → api.telegram.org (needs bot token env).
    Tier 3: mavis session router → OpenClaw gateway → Telegram (Track-A).

    Raises RuntimeError with concatenated details only when **all** tiers
    fail. The caller (`send_message`) catches this and writes the failure
    to `risp_telegram_failures.log` so the user can investigate.
    """
    chat_id, thread_id = _parse_requester(session_id)
    if not chat_id:
        chat_id = os.environ.get("RISP_TELEGRAM_CHAT_ID") or os.environ.get("TELEGRAM_OWNER_CHAT_ID")

    if not chat_id:
        return  # No destination — log-only is fine.

    if thread_id is None:
        env_thread = os.environ.get("RISP_TELEGRAM_THREAD_ID")
        if env_thread:
            try:
                thread_id = int(env_thread)
            except ValueError:
                thread_id = None

    # 1) Preferred: route through the OpenClaw gateway.
    ok, detail = _send_via_openclaw(chat_id, thread_id, message)
    if ok:
        return

    openclaw_detail = str(detail)[:200]

    # 2) Fallback: direct HTTP. Best-effort, may fail (e.g. DNS).
    direct_detail = "(no TELEGRAM_BOT_TOKEN_BLOGGER env)"
    token = os.environ.get("TELEGRAM_BOT_TOKEN_BLOGGER")
    if token:
        direct_ok, dd = _send_direct_http(token, chat_id, thread_id, message)
        if direct_ok:
            return
        direct_detail = str(dd)[:200]

    # 3) Track-A last-resort: mavis communication send via session router.
    mavis_ok, mavis_detail = _send_via_mavis(chat_id, thread_id, message)
    if mavis_ok:
        return
    mavis_detail = str(mavis_detail)[:200]

    # All three tiers failed. Surface a compact, actionable error so the
    # caller (or the user reading the failure log) can debug quickly.
    raise RuntimeError(
        f"telegram delivery failed (3/3 tiers). "
        f"openclaw: {openclaw_detail} | direct_http: {direct_detail} | mavis: {mavis_detail}. "
        f"수동 재시도: openclaw message send --channel telegram --account blogger --target {chat_id}"
        + (f" --thread-id {thread_id}" if thread_id is not None else "")
    )


def send_message(session_id: str, message: str, level: str = "info"):
    """Log and best-effort deliver a RISP signal."""
    timestamp = datetime.now().isoformat()
    payload = {
        "timestamp": timestamp,
        "session_id": session_id,
        "level": level,
        "message": message
    }

    # 현재는 stdout + 로그
    print(f"[{level.upper()}] {message}")

    log_path = Path.home() / ".openclaw" / "workspace-blogger" / "data" / "risp_signaling.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")

    try:
        _send_telegram(message, session_id)
    except Exception as e:
        payload["telegram_error"] = str(e)
        fail_log_path = log_path.with_name("risp_telegram_failures.log")
        with open(fail_log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")
