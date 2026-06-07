#!/usr/bin/env python3
"""One-shot terminal dashboard for the blogger workflow feedback loop.

Shows:
  - jobs in progress today
  - 7-day completion rate
  - currently open alerts
  - 10 most recent retrospectives

This is a CLI one-shot. No web server, no curses UI.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))

from feedback.lib import (  # noqa: E402
    ALERTS_DIR,
    DAILY_SUMMARY_DIR,
    RETRO_DIR,
    WORKFLOW_DIR,
    is_terminal_status,
    list_workflow_slugs,
    load_workflow_state,
    now_kst_iso,
    parse_iso_kst,
    parse_since,
)


# ----------------------------------------------------------------------------
# Sections
# ----------------------------------------------------------------------------


def section_in_progress(today: str) -> list[str]:
    lines: list[str] = ["[in-progress today]"]
    found = 0
    for slug in list_workflow_slugs():
        state = load_workflow_state(slug)
        if not state:
            continue
        ts = parse_iso_kst(state.get("created_at") or "")
        if not ts or ts.date().isoformat() != today:
            continue
        found += 1
        status = state.get("status") or "?"
        title = state.get("title") or slug
        flags = []
        if not is_terminal_status(status):
            flags.append("not-terminal")
        if not state.get("notes"):
            flags.append("no-notes")
        flag_str = f"  ({', '.join(flags)})" if flags else ""
        lines.append(f"  - {slug}  status=`{status}`{flag_str}")
        lines.append(f"      title: {title}")
    if not found:
        lines.append("  (no workflows started today)")
    return lines


def section_completion_rate() -> list[str]:
    since = parse_since("7d")
    now = datetime.now(since.tzinfo)
    total = 0
    completed = 0
    failed = 0
    for slug in list_workflow_slugs():
        state = load_workflow_state(slug)
        if not state:
            continue
        ts = parse_iso_kst(state.get("created_at") or "")
        if not ts or ts < since:
            continue
        total += 1
        status = (state.get("status") or "").upper()
        if status.endswith("_OK") or status in {"COMPLETED", "DONE"}:
            completed += 1
        if status.startswith("FAILED_") or status.startswith("BLOCKED_"):
            failed += 1
    rate = (completed / total * 100.0) if total else 0.0
    lines = ["[7-day completion rate]"]
    lines.append(
        f"  total started: {total}  completed: {completed}  failed: {failed}  rate: {rate:.1f}%"
    )
    return lines


def section_alerts() -> list[str]:
    lines = ["[open alerts]"]
    path = ALERTS_DIR / "alerts.json"
    if not path.exists():
        lines.append("  (no alerts.json yet — run pattern_detector.py first)")
        return lines
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        lines.append("  (alerts.json is corrupt — re-run pattern_detector.py)")
        return lines
    alerts = payload.get("alerts") or []
    if not alerts:
        lines.append("  (none)")
    for a in alerts:
        severity = a.get("severity") or "?"
        atype = a.get("type") or "?"
        msg = a.get("message") or ""
        lines.append(f"  - [{severity}] {atype}: {msg}")
    return lines


def section_recent_retrospectives() -> list[str]:
    lines = ["[recent retrospectives (max 10)]"]
    if not RETRO_DIR.exists():
        lines.append("  (no retrospectives written yet)")
        return lines
    candidates: list[tuple[datetime, Path]] = []
    for sidecar in RETRO_DIR.rglob("*.json"):
        try:
            mtime = datetime.fromtimestamp(sidecar.stat().st_mtime)
        except OSError:
            continue
        candidates.append((mtime, sidecar))
    candidates.sort(key=lambda pair: pair[0], reverse=True)
    for mtime, sidecar in candidates[:10]:
        try:
            data = json.loads(sidecar.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            lines.append(f"  - {sidecar.name}  (corrupt sidecar)")
            continue
        slug = data.get("slug") or sidecar.stem
        lessons = data.get("lessons_learned") or []
        lines.append(
            f"  - {mtime.date().isoformat()}  {slug}  ({len(lessons)} lessons)"
        )
    if not candidates:
        lines.append("  (none)")
    return lines


# ----------------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description="Terminal dashboard for the feedback loop")
    parser.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        help="Output format. Default: text",
    )
    args = parser.parse_args()

    today = now_kst_iso()[:10]
    sections: list[list[str]] = [
        section_in_progress(today),
        section_completion_rate(),
        section_alerts(),
        section_recent_retrospectives(),
    ]

    if args.format == "json":
        json_payload = {
            "generated_at": now_kst_iso(),
            "today": today,
            "sections": [s for s in sections],
        }
        print(json.dumps(json_payload, ensure_ascii=False, indent=2))
        return 0

    print(f"=== Blogger feedback dashboard (KST {today}) ===")
    print()
    for section in sections:
        for line in section:
            print(line)
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
