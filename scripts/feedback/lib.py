#!/usr/bin/env python3
"""Shared utilities for the feedback loop.

Pure read/analyze utilities, no side effects, no external deps. All
time handling is KST. Used by retrospective, pattern_detector, daily_summary,
dashboard, and memory_updater scripts.
"""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable


KST = timezone(timedelta(hours=9))


def _resolve_workspace() -> Path:
    """Return the workspace directory.

    Honors `FEEDBACK_WORKSPACE` env var so tests and CI can redirect
    reads/writes to an isolated directory.
    """
    override = __import__("os").environ.get("FEEDBACK_WORKSPACE")
    if override:
        return Path(override)
    return Path("/Users/noah/.openclaw/workspace-blogger")


WORKSPACE = _resolve_workspace()
WORKFLOW_DIR = WORKSPACE / "data" / "workflow-runs"
IMAGE_PLAN_DIR = WORKSPACE / "data" / "image-plans"
RETRO_DIR = WORKSPACE / "data" / "retrospectives"
ALERTS_DIR = WORKSPACE / "data" / "feedback"
DAILY_SUMMARY_DIR = WORKSPACE / "data" / "daily-summary"
RISP_PROGRESS = WORKSPACE / "data" / "risp_progress.jsonl"
RISP_SIGNALING = WORKSPACE / "data" / "risp_signaling.log"
RISP_TELEGRAM_FAILURES = WORKSPACE / "data" / "risp_telegram_failures.log"
SNS_PUBLISH_LOG = WORKSPACE / "data" / "sns_publish_log.jsonl"
SNS_V3_RUNS = WORKSPACE / "data" / "sns_v3_runs.jsonl"
MAMAVIS_MEMORY = Path("/Users/noah/.mavis/agents/mavis/memory/MEMORY.md")


# ----------------------------------------------------------------------------
# Time helpers
# ----------------------------------------------------------------------------


def now_kst() -> datetime:
    return datetime.now(KST)


def now_kst_iso() -> str:
    return now_kst().isoformat(timespec="seconds")


def today_kst() -> str:
    """Return YYYY-MM-DD in KST."""
    return now_kst().date().isoformat()


def parse_iso_kst(value: str) -> datetime | None:
    """Parse an ISO-8601 timestamp. Returns None on failure."""
    if not value:
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=KST)
    return dt.astimezone(KST)


def ymd(dt: datetime) -> str:
    return dt.astimezone(KST).date().isoformat()


def parse_since(since: str) -> datetime:
    """Parse a duration like '7d', '30d', '24h' into a past datetime in KST."""
    match = re.fullmatch(r"(\d+)\s*([dhmw])", since.strip().lower())
    if not match:
        raise ValueError(f"invalid --since value: {since!r} (use e.g. 7d, 24h, 4w)")
    amount = int(match.group(1))
    unit = match.group(2)
    delta = {
        "h": timedelta(hours=amount),
        "d": timedelta(days=amount),
        "w": timedelta(weeks=amount),
        "m": timedelta(days=amount * 30),
    }[unit]
    return now_kst() - delta


# ----------------------------------------------------------------------------
# JSONL readers
# ----------------------------------------------------------------------------


def iter_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    """Yield one JSON object per non-blank line. Skips corrupt lines."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            yield json.loads(line)
        except json.JSONDecodeError:
            continue


def load_risp_progress() -> list[dict[str, Any]]:
    return list(iter_jsonl(RISP_PROGRESS))


def load_risp_signaling() -> list[dict[str, Any]]:
    return list(iter_jsonl(RISP_SIGNALING))


def load_sns_publish() -> list[dict[str, Any]]:
    return list(iter_jsonl(SNS_PUBLISH_LOG))


# ----------------------------------------------------------------------------
# Workflow state
# ----------------------------------------------------------------------------


def list_workflow_slugs() -> list[str]:
    if not WORKFLOW_DIR.exists():
        return []
    return sorted(p.stem for p in WORKFLOW_DIR.glob("*.json"))


def load_workflow_state(slug: str) -> dict[str, Any] | None:
    path = WORKFLOW_DIR / f"{slug}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def save_workflow_state(slug: str, state: dict[str, Any]) -> Path:
    WORKFLOW_DIR.mkdir(parents=True, exist_ok=True)
    path = WORKFLOW_DIR / f"{slug}.json"
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


# ----------------------------------------------------------------------------
# Image plan helpers
# ----------------------------------------------------------------------------


def load_image_plan(slug: str) -> dict[str, Any] | None:
    path = IMAGE_PLAN_DIR / f"{slug}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


# ----------------------------------------------------------------------------
# Stage helpers
# ----------------------------------------------------------------------------


AUDIT_STAGES = ["draft", "images", "prebuild", "precommit", "complete"]


def is_audit_status_ok(status: str) -> bool:
    return status.startswith("AUDIT_") and status.endswith("_OK")


def is_terminal_status(status: str) -> bool:
    """Status values that indicate the job is finished (success or blocked)."""
    if not status:
        return False
    upper = status.upper()
    if upper.endswith("_OK"):
        return True
    if upper.startswith("BLOCKED_") or upper.startswith("FAILED_"):
        return True
    return upper in {"COMPLETED", "DONE"}


# ----------------------------------------------------------------------------
# Time arithmetic
# ----------------------------------------------------------------------------


def safe_subtract_seconds(later: str | None, earlier: str | None) -> float | None:
    a = parse_iso_kst(earlier) if earlier else None
    b = parse_iso_kst(later) if later else None
    if not a or not b:
        return None
    return max(0.0, (b - a).total_seconds())


def fmt_duration(seconds: float | int | None) -> str:
    if seconds is None:
        return "n/a"
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds}s"
    minutes, sec = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes}m{sec:02d}s"
    hours, min_ = divmod(minutes, 60)
    if hours < 24:
        return f"{hours}h{min_:02d}m"
    days, hr = divmod(hours, 24)
    return f"{days}d{hr:02d}h"


# ----------------------------------------------------------------------------
# Slug normalization
# ----------------------------------------------------------------------------


SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,120}$")


def validate_slug(slug: str) -> None:
    if not SLUG_RE.fullmatch(slug):
        raise SystemExit(
            "[BLOCKED] invalid slug. Use lowercase letters, numbers, and hyphens only."
        )


# ----------------------------------------------------------------------------
# Aggregate helpers
# ----------------------------------------------------------------------------


def group_by(items: list[dict[str, Any]], key_fn) -> dict[Any, list[dict[str, Any]]]:
    out: dict[Any, list[dict[str, Any]]] = defaultdict(list)
    for item in items:
        out[key_fn(item)].append(item)
    return out


def top_n(counter: Counter, n: int = 3) -> list[tuple[Any, int]]:
    return counter.most_common(n)


# ----------------------------------------------------------------------------
# Lessons learned extractor
# ----------------------------------------------------------------------------


def extract_lessons(
    workflow: dict[str, Any],
    risp_entries: list[dict[str, Any]],
    image_plan: dict[str, Any] | None,
    telegram_outcomes: dict[str, int],
) -> list[str]:
    """Return a list of human-readable lessons learned from one job."""
    lessons: list[str] = []

    review = workflow.get("review") or {}
    minimax_revisions = int(review.get("minimax_revisions") or 0)
    if minimax_revisions < 2:
        lessons.append(
            f"Minimax {minimax_revisions}회 보완으로 draft audit 차단 가능 → 다음엔 record-text-review에서 2회 강제"
        )

    if review.get("humanize_korean") not in {"done", "completed", "ok"}:
        lessons.append("humanize-korean 통과 기록 누락 → draft audit에 humanize_korean 게이트 추가")

    if review.get("poetry_rhythm") not in {"done", "completed", "ok"}:
        lessons.append("운문/리듬 검토 기록 누락 → draft audit에 poetry_rhythm 게이트 추가")

    claude = review.get("claude")
    gpt = review.get("gpt_fallback")
    if claude in {"failed", "skipped"} and gpt not in {"done", "completed", "ok", "not_needed"}:
        lessons.append("Claude 1차 검토 실패 + GPT fallback 미기록 → 검수 2단계 강제")

    if image_plan is not None:
        assets = image_plan.get("assets") or []
        fallback_count = 0
        for asset in assets:
            attempts = asset.get("attempts") or []
            if len(attempts) > 1:
                fallback_count += 1
        if fallback_count:
            lessons.append(
                f"이미지 {fallback_count}개가 fallback 사용 → image_checker가 모델별 성공률 추적 필요"
            )

    sessions = {entry.get("session_id") for entry in risp_entries}
    if len(sessions) > 1:
        lessons.append(
            f"RISP session이 {len(sessions)}개로 분할됨 → 단일 session_id로 일원화"
        )

    begin_count = sum(1 for e in risp_entries if e.get("event") == "begin")
    summary_count = sum(1 for e in risp_entries if e.get("event") == "summary")
    if begin_count > 3 and summary_count == 0:
        lessons.append(
            f"begin {begin_count}회 / summary 0회 → RISP 무한 루프 패턴, BLOCKED_LOOP 후보"
        )

    failures = telegram_outcomes.get("failure", 0)
    successes = telegram_outcomes.get("success", 0)
    if failures and successes:
        lessons.append(
            f"텔레그램 발송 {successes}건 성공 / {failures}건 실패 → Track A fallback chain 점검"
        )

    if not lessons:
        lessons.append("이번 작업은 주요 게이트를 모두 통과함 — 회고 템플릿/가드 유지")

    return lessons
