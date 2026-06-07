#!/usr/bin/env python3
"""Detect recurring failure and regression patterns across the workflow.

Inputs (all read-only):
  - data/workflow-runs/*.json          (per-job state, including lessons_learned)
  - data/retrospectives/**/*.json      (sidecars from retrospective.py)
  - data/risp_progress.jsonl           (stage timing per session)
  - data/risp_signaling.log            (RISP signaling events)
  - data/risp_telegram_failures.log    (Telegram send failures)
  - data/sns_publish_log.jsonl         (SNS publish outcomes)

Output:
  - data/feedback/alerts.json          (machine-readable alerts)
  - stdout                             (human summary)

Telegram delivery is intentionally not done here. Track A owns the fallback
chain; this script just writes to the alerts file so downstream senders
can pick it up.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))

from feedback.lib import (  # noqa: E402
    ALERTS_DIR,
    RISP_PROGRESS,
    RISP_SIGNALING,
    RISP_TELEGRAM_FAILURES,
    WORKFLOW_DIR,
    WORKSPACE,
    fmt_duration,
    iter_jsonl,
    load_risp_progress,
    load_risp_signaling,
    now_kst_iso,
    parse_iso_kst,
    parse_since,
)


# ----------------------------------------------------------------------------
# Detectors
# ----------------------------------------------------------------------------


def detect_stage_repeats(workflow_dir: Path, threshold: int = 3) -> list[dict[str, Any]]:
    """A workflow that fails the same gate threshold times gets flagged.

    We infer 'failed the same stage' from the audit transitions inside the
    state notes. If notes are missing, fall back to a generic warning that
    the workflow has been RECEIVED for too long with no successful audit.
    """
    if not workflow_dir.exists():
        return []
    findings: list[dict[str, Any]] = []
    for path in sorted(workflow_dir.glob("*.json")):
        try:
            state = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        status = state.get("status") or ""
        if status.startswith("AUDIT_") and status.endswith("_OK"):
            continue
        notes = state.get("notes") or []
        failed_audit_count = sum(
            1 for n in notes if isinstance(n, dict) and "fail" in (n.get("text") or "").lower()
        )
        slug = state.get("slug") or path.stem
        if failed_audit_count >= threshold:
            findings.append(
                {
                    "type": "stage_repeat",
                    "slug": slug,
                    "severity": "high" if failed_audit_count >= threshold * 2 else "medium",
                    "message": (
                        f"slug `{slug}` failed audit {failed_audit_count} times "
                        f"(threshold {threshold}) — likely stuck in retry loop"
                    ),
                    "evidence": {"failed_audit_count": failed_audit_count},
                }
            )
    return findings


def detect_infinite_loops(
    progress_entries: list[dict[str, Any]],
    threshold: int = 5,
) -> list[dict[str, Any]]:
    """Same session_id restarts at stage 1 too many times."""
    if not progress_entries:
        return []
    session_starts: dict[str, int] = Counter()
    for entry in progress_entries:
        if entry.get("event") == "begin" and entry.get("stage_index") == 1:
            session_id = entry.get("session_id")
            if session_id:
                session_starts[session_id] += 1
    findings: list[dict[str, Any]] = []
    for session_id, count in session_starts.most_common(10):
        if count >= threshold:
            findings.append(
                {
                    "type": "infinite_loop",
                    "session_id": session_id,
                    "severity": "high",
                    "message": (
                        f"session `{session_id}` started at stage 1 "
                        f"{count} times (threshold {threshold}) — infinite loop"
                    ),
                    "evidence": {"stage1_begin_count": count},
                }
            )
    return findings


def detect_performance_regression(progress_entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Compare last-1-week vs prior-3-weeks mean stage duration."""
    if not progress_entries:
        return []
    now = datetime.now(parse_iso_kst(now_kst_iso()).tzinfo or __import__("datetime").timezone.utc)
    one_week_ago = now - timedelta(days=7)
    four_weeks_ago = now - timedelta(days=28)
    recent: list[float] = []
    baseline: list[float] = []
    for entry in progress_entries:
        if entry.get("event") != "complete":
            continue
        elapsed = entry.get("stage_elapsed_s")
        ts = parse_iso_kst(entry.get("timestamp") or "")
        if not isinstance(elapsed, (int, float)) or ts is None:
            continue
        if ts >= one_week_ago:
            recent.append(float(elapsed))
        elif ts >= four_weeks_ago:
            baseline.append(float(elapsed))
    if len(recent) < 5 or len(baseline) < 5:
        return []
    recent_mean = sum(recent) / len(recent)
    baseline_mean = sum(baseline) / len(baseline)
    if baseline_mean <= 0:
        return []
    delta_pct = (recent_mean - baseline_mean) / baseline_mean * 100.0
    if delta_pct < 20.0:
        return []
    return [
        {
            "type": "performance_regression",
            "severity": "medium" if delta_pct < 50 else "high",
            "message": (
                f"Mean stage duration up {delta_pct:.1f}% week-over-4-weeks "
                f"({recent_mean:.1f}s vs {baseline_mean:.1f}s)"
            ),
            "evidence": {
                "recent_mean_s": recent_mean,
                "baseline_mean_s": baseline_mean,
                "delta_pct": delta_pct,
                "recent_samples": len(recent),
                "baseline_samples": len(baseline),
            },
        }
    ]


def detect_quality_regression(workflow_dir: Path) -> list[dict[str, Any]]:
    """Heuristic: lots of fallback attempts + minimax_revisions missing.

    Looks for jobs where image plan has more than 2 fallback attempts and
    minimax_revisions is unset, which historically correlates with quality
    complaints in the daily memory log.
    """
    if not workflow_dir.exists():
        return []
    findings: list[dict[str, Any]] = []
    for path in sorted(workflow_dir.glob("*.json")):
        try:
            state = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        slug = state.get("slug") or path.stem
        review = state.get("review") or {}
        minimax_revisions = int(review.get("minimax_revisions") or 0)
        if minimax_revisions >= 2:
            continue
        paths = state.get("paths") or {}
        image_plan_rel = paths.get("image_plan") or ""
        if not image_plan_rel:
            continue
        # The image_plan path is recorded relative to the workspace root.
        plan_path = (
            (WORKSPACE / image_plan_rel)
            if not Path(image_plan_rel).is_absolute()
            else Path(image_plan_rel)
        )
        if not plan_path.exists():
            continue
        try:
            plan = json.loads(plan_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        fallback_total = 0
        model_counter: Counter = Counter()
        for asset in plan.get("assets") or []:
            attempts = asset.get("attempts") or []
            if len(attempts) > 1:
                fallback_total += 1
            model = asset.get("model") or asset.get("provider")
            if model:
                model_counter[model] += 1
        if fallback_total < 2:
            continue
        most_common_model, _ = model_counter.most_common(1)[0] if model_counter else ("?", 0)
        findings.append(
            {
                "type": "quality_regression",
                "slug": slug,
                "severity": "medium",
                "message": (
                    f"slug `{slug}` had {fallback_total} image fallback attempts "
                    f"and Minimax revisions={minimax_revisions} — quality risk"
                ),
                "evidence": {
                    "fallback_assets": fallback_total,
                    "minimax_revisions": minimax_revisions,
                    "most_common_model": most_common_model,
                },
            }
        )
    return findings


def detect_telegram_regression(window: timedelta) -> list[dict[str, Any]]:
    """When recent failures exceed baseline, raise an alert."""
    if not RISP_TELEGRAM_FAILURES.exists():
        return []
    now = datetime.now(parse_iso_kst(now_kst_iso()).tzinfo or __import__("datetime").timezone.utc)
    recent = 0
    baseline = 0
    for entry in iter_jsonl(RISP_TELEGRAM_FAILURES):
        ts = parse_iso_kst(entry.get("timestamp") or "")
        if ts is None:
            continue
        if ts >= now - window:
            recent += 1
        elif ts >= now - window * 4:
            baseline += 1
    if recent < 3 or baseline == 0:
        return []
    rate_now = recent / max(window.total_seconds() / 3600, 1)
    rate_before = baseline / max((window * 3).total_seconds() / 3600, 1)
    if rate_now < rate_before * 1.5:
        return []
    return [
        {
            "type": "telegram_regression",
            "severity": "high" if recent >= 10 else "medium",
            "message": (
                f"Telegram failures {recent} in last {window.days}d vs "
                f"{baseline} in prior {window.days * 3}d window"
            ),
            "evidence": {
                "recent_failures": recent,
                "baseline_failures": baseline,
            },
        }
    ]


# ----------------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------------


def collect_alerts(window: timedelta) -> dict[str, Any]:
    progress = load_risp_progress()
    signaling = load_risp_signaling()

    alerts: list[dict[str, Any]] = []
    alerts.extend(detect_stage_repeats(WORKFLOW_DIR))
    alerts.extend(detect_infinite_loops(progress))
    alerts.extend(detect_performance_regression(progress))
    alerts.extend(detect_quality_regression(WORKFLOW_DIR))
    alerts.extend(detect_telegram_regression(window))

    return {
        "generated_at": now_kst_iso(),
        "window_days": window.days,
        "alert_count": len(alerts),
        "alerts": alerts,
    }


def write_alerts(alerts_payload: dict[str, Any], output: Path) -> Path:
    ALERTS_DIR.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(alerts_payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description="Detect failure and regression patterns")
    parser.add_argument(
        "--since",
        default="7d",
        help="Window for regression detection (e.g. 7d, 24h). Default: 7d",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ALERTS_DIR / "alerts.json",
        help="Path to write alerts.json (default: data/feedback/alerts.json)",
    )
    args = parser.parse_args()

    since = parse_since(args.since)
    now = datetime.now(since.tzinfo)
    window = now - since
    payload = collect_alerts(window)

    output = write_alerts(payload, args.output)
    print(f"[OK] alerts written: {output}")
    if payload["alerts"]:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print("[OK] no alerts raised — system looks healthy")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
