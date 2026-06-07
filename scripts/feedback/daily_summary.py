#!/usr/bin/env python3
"""Summarize a day's work (default: yesterday KST) into a markdown report.

Counts:
  - workflows started vs reached a terminal status
  - average total elapsed time
  - top 3 blockers (from workflow state + RISP signaling)
  - suggested improvements

Inputs:
  - data/workflow-runs/*.json
  - data/retrospectives/**/*.json
  - data/risp_progress.jsonl
  - data/risp_signaling.log

Output:
  - data/daily-summary/{YYYY-MM-DD}.md  (and stdout)
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
    DAILY_SUMMARY_DIR,
    RETRO_DIR,
    RISP_PROGRESS,
    RISP_SIGNALING,
    RISP_TELEGRAM_FAILURES,
    SNS_PUBLISH_LOG,
    WORKFLOW_DIR,
    fmt_duration,
    is_terminal_status,
    iter_jsonl,
    list_workflow_slugs,
    load_workflow_state,
    now_kst_iso,
    parse_iso_kst,
)


# ----------------------------------------------------------------------------
# Aggregations
# ----------------------------------------------------------------------------


def workflows_on_date(date: str) -> list[dict[str, Any]]:
    """Workflows whose created_at falls on the given YYYY-MM-DD (KST)."""
    out: list[dict[str, Any]] = []
    for slug in list_workflow_slugs():
        state = load_workflow_state(slug)
        if not state:
            continue
        ts = parse_iso_kst(state.get("created_at") or "")
        if ts and ts.date().isoformat() == date:
            out.append(state)
    return out


def retrospectives_on_date(date: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    retro_dir = RETRO_DIR / date
    if not retro_dir.exists():
        return out
    for sidecar in retro_dir.glob("*.json"):
        try:
            out.append(json.loads(sidecar.read_text(encoding="utf-8")))
        except json.JSONDecodeError:
            continue
    return out


def risp_events_on_date(date: str) -> list[dict[str, Any]]:
    out = []
    for entry in iter_jsonl(RISP_PROGRESS):
        ts = parse_iso_kst(entry.get("timestamp") or "")
        if ts and ts.date().isoformat() == date:
            out.append(entry)
    return out


def signaling_summary(date: str) -> dict[str, int]:
    info = warn = error = 0
    for entry in iter_jsonl(RISP_SIGNALING):
        ts = parse_iso_kst(entry.get("timestamp") or "")
        if not ts or ts.date().isoformat() != date:
            continue
        level = (entry.get("level") or "").lower()
        if level == "error":
            error += 1
        elif level == "warn":
            warn += 1
        else:
            info += 1
    return {"info": info, "warn": warn, "error": error}


def telegram_failure_count(date: str) -> int:
    count = 0
    for entry in iter_jsonl(RISP_TELEGRAM_FAILURES):
        ts = parse_iso_kst(entry.get("timestamp") or "")
        if ts and ts.date().isoformat() == date and entry.get("telegram_error"):
            count += 1
    return count


def sns_publish_count(date: str) -> int:
    count = 0
    for entry in iter_jsonl(SNS_PUBLISH_LOG):
        ts = parse_iso_kst(entry.get("timestamp") or "")
        if ts and ts.date().isoformat() == date:
            count += 1
    return count


def average_total_seconds(states: list[dict[str, Any]]) -> float | None:
    samples: list[float] = []
    for state in states:
        created = parse_iso_kst(state.get("created_at") or "")
        updated = parse_iso_kst(state.get("updated_at") or "")
        if not created or not updated:
            continue
        seconds = (updated - created).total_seconds()
        if seconds >= 0:
            samples.append(seconds)
    if not samples:
        return None
    return sum(samples) / len(samples)


def top_blockers(states: list[dict[str, Any]], risp_events: list[dict[str, Any]]) -> list[str]:
    """Return up to 3 blocker descriptions."""
    blockers: Counter = Counter()

    for state in states:
        if is_terminal_status(state.get("status") or ""):
            continue
        status = state.get("status") or "UNKNOWN"
        blockers[f"workflow stuck at status `{status}`"] += 1

    for entry in risp_events:
        if entry.get("event") == "failed":
            message = entry.get("message") or "(no message)"
            blockers[f"RISP failed event: {message[:80]}"] += 1

    for entry in iter_jsonl(RISP_SIGNALING):
        ts = parse_iso_kst(entry.get("timestamp") or "")
        if not ts or entry.get("level") != "error":
            continue
        message = entry.get("message") or "(no message)"
        blockers[f"signaling error: {message[:80]}"] += 1

    return [b for b, _ in blockers.most_common(3)]


def improvement_suggestions(
    states: list[dict[str, Any]],
    retros: list[dict[str, Any]],
    blockers: list[str],
    telegram_failures: int,
) -> list[str]:
    suggestions: list[str] = []
    if any(not is_terminal_status(s.get("status") or "") for s in states):
        suggestions.append(
            "Some jobs are still in non-terminal status. Run `dashboard.py` and "
            "focus the earliest `RECEIVED` workflow first."
        )
    if telegram_failures >= 3:
        suggestions.append(
            "Telegram failure count >= 3 today — verify Track A's fallback chain "
            "is healthy and consider re-running the most recent send."
        )
    lessons_seen: list[str] = []
    for retro in retros:
        for lesson in retro.get("lessons_learned") or []:
            if lesson not in lessons_seen:
                lessons_seen.append(lesson)
    if lessons_seen:
        suggestions.append(
            "Top retrospective lessons to discuss with 형님: "
            + "; ".join(lessons_seen[:2])
        )
    if not suggestions:
        suggestions.append("No improvement actions needed — system looks healthy.")
    return suggestions


# ----------------------------------------------------------------------------
# Markdown rendering
# ----------------------------------------------------------------------------


def render_markdown(
    date: str,
    states: list[dict[str, Any]],
    retros: list[dict[str, Any]],
    risp_events: list[dict[str, Any]],
    signaling: dict[str, int],
    telegram_failures: int,
    sns_publish: int,
) -> str:
    completed = [s for s in states if is_terminal_status(s.get("status") or "")]
    failed = [
        s for s in states
        if (s.get("status") or "").upper().startswith("FAILED_")
    ]
    avg_total = average_total_seconds(states)
    blockers = top_blockers(states, risp_events)
    suggestions = improvement_suggestions(states, retros, blockers, telegram_failures)

    lines: list[str] = []
    lines.append(f"# Daily summary — {date} (KST)")
    lines.append("")
    lines.append(f"- Generated at: {now_kst_iso()}")
    lines.append(f"- Workflows started: {len(states)}")
    lines.append(f"- Workflows reached terminal status: {len(completed)}")
    lines.append(f"- Workflows explicitly FAILED: {len(failed)}")
    lines.append(f"- Average total elapsed: {fmt_duration(avg_total)}")
    lines.append(f"- Retrospectives written: {len(retros)}")
    lines.append(f"- RISP signaling: info={signaling['info']} warn={signaling['warn']} error={signaling['error']}")
    lines.append(f"- Telegram send failures: {telegram_failures}")
    lines.append(f"- SNS publish events: {sns_publish}")
    lines.append("")

    lines.append("## Top 3 blockers")
    lines.append("")
    if blockers:
        for b in blockers:
            lines.append(f"- {b}")
    else:
        lines.append("- _No blockers detected._")
    lines.append("")

    lines.append("## Workflows")
    lines.append("")
    if states:
        lines.append("| Slug | Status | Created | Updated | Total |")
        lines.append("| --- | --- | --- | --- | --- |")
        for s in states:
            slug = s.get("slug") or "?"
            status = s.get("status") or "?"
            created = s.get("created_at") or "-"
            updated = s.get("updated_at") or "-"
            cdt = parse_iso_kst(created)
            udt = parse_iso_kst(updated)
            total = fmt_duration((udt - cdt).total_seconds()) if cdt and udt else "-"
            lines.append(f"| {slug} | `{status}` | {created} | {updated} | {total} |")
    else:
        lines.append("_No workflows started on this date._")
    lines.append("")

    lines.append("## Retrospectives")
    lines.append("")
    if retros:
        for r in retros:
            lessons = r.get("lessons_learned") or []
            head = r.get("slug") or r.get("retrospective_path") or "?"
            lines.append(f"- **{head}** — {len(lessons)} lessons learned")
    else:
        lines.append("- _No retrospectives written on this date._")
    lines.append("")

    lines.append("## Suggested improvements")
    lines.append("")
    for s in suggestions:
        lines.append(f"- {s}")
    lines.append("")

    return "\n".join(lines) + "\n"


# ----------------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------------


def cmd_run(args: argparse.Namespace) -> int:
    if args.date:
        date = args.date
    else:
        yesterday = (datetime.now() - timedelta(days=1)).date()
        date = yesterday.isoformat()
    states = workflows_on_date(date)
    retros = retrospectives_on_date(date)
    risp_events = risp_events_on_date(date)
    signaling = signaling_summary(date)
    telegram_failures = telegram_failure_count(date)
    sns_publish = sns_publish_count(date)

    body = render_markdown(
        date,
        states,
        retros,
        risp_events,
        signaling,
        telegram_failures,
        sns_publish,
    )
    out_path = DAILY_SUMMARY_DIR / f"{date}.md"
    DAILY_SUMMARY_DIR.mkdir(parents=True, exist_ok=True)
    out_path.write_text(body, encoding="utf-8")
    print(f"[OK] daily summary written: {out_path}")
    print()
    print(body)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a daily summary markdown file")
    parser.add_argument(
        "--date",
        help="YYYY-MM-DD in KST. Defaults to yesterday KST.",
    )
    args = parser.parse_args()
    return cmd_run(args)


if __name__ == "__main__":
    raise SystemExit(main())
