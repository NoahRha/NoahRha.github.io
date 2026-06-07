#!/usr/bin/env python3
"""Suggest MEMORY.md updates from alerts and retrospectives.

This script NEVER commits or writes to MEMORY.md directly. It produces a
preview (stdout + markdown) and a `--apply` mode that prints the same diff
to stdout and an optional --output path. The human (형님) reviews the
preview and decides what to commit.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))

from feedback.lib import (  # noqa: E402
    ALERTS_DIR,
    MAMAVIS_MEMORY,
    RETRO_DIR,
    WORKFLOW_DIR,
    iter_jsonl,
    now_kst_iso,
    parse_iso_kst,
)


# ----------------------------------------------------------------------------
# Suggestion generation
# ----------------------------------------------------------------------------


LESSON_TAG = "### Track C 자동 lesson 후보"
MEMORY_HEADER_RE = re.compile(r"^##\s", re.MULTILINE)


def _gather_alerts() -> list[dict[str, Any]]:
    alerts_path = ALERTS_DIR / "alerts.json"
    if not alerts_path.exists():
        return []
    try:
        return json.loads(alerts_path.read_text(encoding="utf-8")).get("alerts", [])
    except json.JSONDecodeError:
        return []


def _gather_lessons() -> list[tuple[str, str]]:
    """Return (slug, lesson) tuples for every retrospective sidecar."""
    out: list[tuple[str, str]] = []
    if not RETRO_DIR.exists():
        return out
    for sidecar in RETRO_DIR.rglob("*.json"):
        try:
            data = json.loads(sidecar.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        slug = data.get("slug") or sidecar.stem
        for lesson in data.get("lessons_learned") or []:
            out.append((slug, lesson))
    return out


def build_suggestions() -> list[dict[str, str]]:
    alerts = _gather_alerts()
    lessons = _gather_lessons()

    counter: Counter = Counter()
    by_type: dict[str, list[str]] = {}

    for alert in alerts:
        atype = alert.get("type") or "unknown"
        key = (atype, alert.get("message") or "(no message)")
        counter[key] += 1
        by_type.setdefault(atype, []).append(alert.get("message") or "")

    for slug, lesson in lessons:
        key = ("retrospective", lesson)
        counter[key] += 1
        by_type.setdefault("retrospective", []).append(f"{slug}: {lesson}")

    suggestions: list[dict[str, str]] = []
    for (atype, message), count in counter.most_common(20):
        suggestions.append(
            {
                "type": atype,
                "message": message,
                "count": str(count),
                "rationale": (
                    f"Observed {count} time(s) across alerts and retrospectives"
                ),
            }
        )
    return suggestions


# ----------------------------------------------------------------------------
# Preview rendering
# ----------------------------------------------------------------------------


def render_preview(suggestions: list[dict[str, str]]) -> str:
    today = now_kst_iso()[:10]
    lines: list[str] = []
    lines.append(f"# Track C memory preview — {today}")
    lines.append("")
    lines.append(
        "This preview was generated automatically by `memory_updater.py suggest`. "
        "Do NOT commit it without human review. Suggested append location: "
        f"`{MAMAVIS_MEMORY}`."
    )
    lines.append("")
    if not suggestions:
        lines.append("_No new lesson candidates._")
        return "\n".join(lines) + "\n"

    lines.append(f"## Candidate lessons ({len(suggestions)})")
    lines.append("")
    for idx, s in enumerate(suggestions, 1):
        lines.append(
            f"{idx}. **{s['type']}** (x{s['count']}) — {s['message']}"
        )
        lines.append(f"   - Rationale: {s['rationale']}")
    lines.append("")
    lines.append("## Markdown block ready to paste under MEMORY.md")
    lines.append("")
    lines.append("```markdown")
    lines.append(LESSON_TAG)
    for s in suggestions[:3]:
        lines.append("")
        lines.append(f"### {s['type']} 자동화 lesson ({now_kst_iso()[:10]})")
        lines.append("Type: lesson")
        lines.append("")
        lines.append(s["message"])
        lines.append("")
    lines.append("```")
    lines.append("")
    return "\n".join(lines) + "\n"


def render_diff(suggestions: list[dict[str, str]]) -> str:
    """Print a unified-diff-ish preview of what would be appended to MEMORY.md."""
    today = now_kst_iso()[:10]
    lines: list[str] = []
    lines.append(f"--- {MAMAVIS_MEMORY} (current)")
    lines.append(f"+++ {MAMAVIS_MEMORY} (proposed)")
    lines.append(f"@@ appended at {today} @@")
    lines.append(f"+{LESSON_TAG} ({today})")
    for s in suggestions[:3]:
        lines.append(f"+")
        lines.append(f"+### {s['type']} lesson")
        lines.append(f"+Type: lesson")
        lines.append(f"+")
        lines.append(f"+{s['message']}")
    return "\n".join(lines) + "\n"


# ----------------------------------------------------------------------------
# Apply (preview only — never writes to MEMORY.md)
# ----------------------------------------------------------------------------


def cmd_suggest(args: argparse.Namespace) -> int:
    suggestions = build_suggestions()
    print(render_preview(suggestions))
    return 0


def cmd_apply(args: argparse.Namespace) -> int:
    suggestions = build_suggestions()
    diff = render_diff(suggestions)
    print(diff)
    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(
            render_preview(suggestions), encoding="utf-8"
        )
        print(f"[OK] preview written: {args.output}")
    print(
        "[REMINDER] This script NEVER modifies "
        f"{MAMAVIS_MEMORY}. Review the diff above and commit manually if approved."
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Suggest MEMORY.md updates (preview only)")
    sub = parser.add_subparsers(dest="command", required=True)

    suggest = sub.add_parser("suggest", help="Print a human-readable preview of candidate lessons")
    suggest.set_defaults(func=cmd_suggest)

    apply = sub.add_parser("apply", help="Show the proposed diff (still preview-only)")
    apply.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Always on; this script never writes to MEMORY.md",
    )
    apply.add_argument(
        "--output",
        type=Path,
        help="Optional path to write the preview markdown to",
    )
    apply.set_defaults(func=cmd_apply)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
