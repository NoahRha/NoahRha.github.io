#!/usr/bin/env python3
"""Generate a per-job retrospective markdown report.

Reads the workflow state, image plan, RISP progress, and Telegram/SNS publish
logs for a slug. Emits a single markdown file with timing, stage outcomes,
asset models, Telegram counts, and auto-extracted lessons.

This script is intentionally read-only on the workflow state — it writes a
markdown file and optionally patches the workflow JSON with `retrospective_path`
+ `lessons_learned`. That patch is opt-in via --update-state.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

# Allow running as a script from anywhere.
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
    extract_lessons,
    fmt_duration,
    is_audit_status_ok,
    is_terminal_status,
    iter_jsonl,
    list_workflow_slugs,
    load_image_plan,
    load_risp_progress,
    load_sns_publish,
    load_workflow_state,
    now_kst_iso,
    safe_subtract_seconds,
    save_workflow_state,
    top_n,
    validate_slug,
    ymd,
)


# ----------------------------------------------------------------------------
# Aggregations
# ----------------------------------------------------------------------------


def risp_entries_for_slug(slug: str) -> list[dict[str, Any]]:
    """RISP progress entries that mention the slug in the message body."""
    out = []
    needle = slug.lower()
    for entry in iter_jsonl(RISP_PROGRESS):
        message = (entry.get("message") or "").lower()
        if needle in message:
            out.append(entry)
    return out


def signaling_entries_for_session(session_id: str | None) -> list[dict[str, Any]]:
    if not session_id:
        return []
    out = []
    for entry in iter_jsonl(RISP_SIGNALING):
        if entry.get("session_id") == session_id:
            out.append(entry)
    return out


def telegram_outcomes(workflow: dict[str, Any]) -> dict[str, int]:
    """Tally Telegram send success/failure events for this slug's blog URL."""
    paths = workflow.get("paths") or {}
    post_rel = paths.get("post") or ""
    blog_url = ""

    # Try to pull the public URL from the post file's first link.
    if post_rel:
        post_path = WORKFLOW_DIR.parent / post_rel
        if post_path.exists():
            text = post_path.read_text(encoding="utf-8", errors="replace")
            for line in text.splitlines():
                if "techllm.github.io" in line or "noahrha.github.io" in line:
                    blog_url = line.strip()
                    break

    successes = 0
    failures = 0
    for entry in iter_jsonl(SNS_PUBLISH_LOG):
        if blog_url and entry.get("blog_url") == blog_url:
            successes += 1
    for entry in iter_jsonl(RISP_TELEGRAM_FAILURES):
        if entry.get("session_id") and entry.get("telegram_error"):
            failures += 1
    return {"success": successes, "failure": failures, "blog_url": blog_url}


def image_model_stats(plan: dict[str, Any] | None) -> dict[str, Any]:
    if not plan:
        return {"assets_total": 0, "by_model": {}, "fallback_assets": []}
    assets = plan.get("assets") or []
    by_model: dict[str, int] = {}
    fallback_assets: list[str] = []
    for asset in assets:
        model = (asset.get("model") or asset.get("provider") or "(missing)").strip()
        by_model[model] = by_model.get(model, 0) + 1
        attempts = asset.get("attempts") or []
        if len(attempts) > 1:
            fallback_assets.append(
                f"{asset.get('id') or '(no-id)'} ({len(attempts)} attempts)"
            )
    return {
        "assets_total": len(assets),
        "by_model": by_model,
        "fallback_assets": fallback_assets,
    }


def stage_breakdown(risp_entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Group RISP progress by stage_index. Compute per-stage begin/complete timing."""
    by_stage: dict[int, dict[str, Any]] = {}
    for entry in risp_entries:
        idx = entry.get("stage_index")
        if idx is None:
            continue
        stage = by_stage.setdefault(
            int(idx),
            {
                "stage_index": int(idx),
                "stage_name": entry.get("stage_name") or "",
                "began_at": None,
                "completed_at": None,
                "last_elapsed_s": 0.0,
                "updates": 0,
            },
        )
        event = entry.get("event")
        if event == "begin":
            stage["began_at"] = entry.get("timestamp")
        elif event == "complete":
            stage["completed_at"] = entry.get("timestamp")
        elif event == "update":
            stage["updates"] += 1
        elapsed = entry.get("stage_elapsed_s")
        if isinstance(elapsed, (int, float)):
            stage["last_elapsed_s"] = max(stage["last_elapsed_s"], float(elapsed))
    stages = list(by_stage.values())
    stages.sort(key=lambda s: s["stage_index"])
    for stage in stages:
        stage["duration_s"] = safe_subtract_seconds(stage["completed_at"], stage["began_at"])
    return stages


def detect_stuck_point(stages: list[dict[str, Any]]) -> str | None:
    """If a stage was begun but never completed, return its name."""
    for stage in stages:
        if stage["began_at"] and not stage["completed_at"]:
            return stage["stage_name"] or f"stage {stage['stage_index']}"
    return None


def pick_session_id(risp_entries: list[dict[str, Any]]) -> str | None:
    sessions = [e.get("session_id") for e in risp_entries if e.get("session_id")]
    if not sessions:
        return None
    return max(set(sessions), key=sessions.count)


# ----------------------------------------------------------------------------
# Markdown rendering
# ----------------------------------------------------------------------------


def render_markdown(
    slug: str,
    workflow: dict[str, Any],
    risp_entries: list[dict[str, Any]],
    image_plan: dict[str, Any] | None,
    outcomes: dict[str, int],
) -> str:
    title = workflow.get("title") or slug
    status = workflow.get("status") or "UNKNOWN"
    created = workflow.get("created_at")
    updated = workflow.get("updated_at")
    total_s = safe_subtract_seconds(updated, created)
    review = workflow.get("review") or {}

    stages = stage_breakdown(risp_entries)
    stuck = detect_stuck_point(stages)
    slowest = sorted(
        (s for s in stages if s.get("duration_s") is not None),
        key=lambda s: -(s["duration_s"] or 0.0),
    )[:3]

    image_stats = image_model_stats(image_plan)
    lessons = extract_lessons(workflow, risp_entries, image_plan, outcomes)

    lines: list[str] = []
    lines.append(f"# Retrospective: {slug}")
    lines.append("")
    lines.append(f"- **Title:** {title}")
    lines.append(f"- **Status:** `{status}`  (terminal: {is_terminal_status(status)})")
    lines.append(f"- **Created:** {created or 'n/a'}")
    lines.append(f"- **Updated:** {updated or 'n/a'}")
    lines.append(f"- **Total elapsed:** {fmt_duration(total_s)}")
    lines.append(f"- **Generated at:** {now_kst_iso()}")
    lines.append("")
    lines.append("## Audit gates")
    lines.append("")
    if is_audit_status_ok(status):
        lines.append(f"- Last audit status: `{status}` (PASS)")
    else:
        lines.append(f"- Last audit status: `{status}` (no successful audit yet)")
    gates = workflow.get("required_gates") or []
    if gates:
        lines.append("- Required gates:")
        for gate in gates:
            lines.append(f"  - {gate}")
    else:
        lines.append("- No required_gates listed in workflow state.")
    lines.append("")

    lines.append("## Review fields")
    lines.append("")
    lines.append("| Field | Value |")
    lines.append("| --- | --- |")
    for key in (
        "claude",
        "gpt_fallback",
        "minimax",
        "minimax_revisions",
        "humanize_korean",
        "poetry_rhythm",
    ):
        lines.append(f"| {key} | {review.get(key, '(unset)')} |")
    lines.append("")

    lines.append("## Stage breakdown (from RISP progress)")
    lines.append("")
    if not stages:
        lines.append("_No RISP progress events found for this slug._")
    else:
        lines.append("| Stage | Name | Began | Completed | Duration | Updates |")
        lines.append("| --- | --- | --- | --- | --- | --- |")
        for stage in stages:
            lines.append(
                "| {idx} | {name} | {began} | {done} | {dur} | {upd} |".format(
                    idx=stage["stage_index"],
                    name=stage["stage_name"] or "-",
                    began=stage["began_at"] or "-",
                    done=stage["completed_at"] or "-",
                    dur=fmt_duration(stage["duration_s"]),
                    upd=stage["updates"],
                )
            )
        lines.append("")
        if stuck:
            lines.append(f"- **Stuck point:** `{stuck}` (begin without complete)")
        else:
            lines.append("- **Stuck point:** none — all logged stages have a complete event")
        if slowest:
            lines.append("- **Slowest stages:**")
            for s in slowest:
                lines.append(
                    f"  - stage {s['stage_index']} {s['stage_name']}: {fmt_duration(s['duration_s'])}"
                )
    lines.append("")

    lines.append("## Image plan")
    lines.append("")
    if not image_plan:
        lines.append(f"_No image plan found at `data/image-plans/{slug}.json`._")
    else:
        lines.append(f"- Total assets: {image_stats['assets_total']}")
        if image_stats["by_model"]:
            lines.append("- Models used:")
            for model, count in sorted(image_stats["by_model"].items(), key=lambda kv: -kv[1]):
                lines.append(f"  - {model}: {count}")
        if image_stats["fallback_assets"]:
            lines.append("- Assets that needed more than one attempt (fallback):")
            for entry in image_stats["fallback_assets"]:
                lines.append(f"  - {entry}")
        else:
            lines.append("- No fallback attempts — all assets generated on first try.")
    lines.append("")

    lines.append("## Telegram / SNS publish outcomes")
    lines.append("")
    lines.append(f"- Blog URL (if any): {outcomes.get('blog_url') or '(not detected)'}")
    lines.append(f"- SNS publish successes recorded: {outcomes.get('success', 0)}")
    lines.append(f"- Telegram failures recorded: {outcomes.get('failure', 0)}")
    if not outcomes.get("success") and not outcomes.get("failure"):
        lines.append("- _No matching SNS publish or Telegram failure events were found._")
    lines.append("")

    lines.append("## Lessons learned (auto-extracted)")
    lines.append("")
    for lesson in lessons:
        lines.append(f"- {lesson}")
    lines.append("")

    lines.append("## Suggested next actions")
    lines.append("")
    if stuck:
        lines.append(f"- Unblock stage `{stuck}` before re-running the workflow.")
    if not is_audit_status_ok(status):
        lines.append("- Run `blog_workflow_guard.py audit --stage prebuild` to record the gate state.")
    if review.get("minimax_revisions", 0) < 2:
        lines.append("- Re-run `blog_sns_harness.py record-text-review --minimax-revisions 2`.")
    if image_stats["fallback_assets"]:
        lines.append("- Inspect fallback assets: prompt may need a stronger style prefix.")
    if outcomes.get("failure", 0) > 0:
        lines.append("- Trigger Track A's telegram fallback chain to retry failed sends.")
    if not stuck and is_audit_status_ok(status) and not image_stats["fallback_assets"]:
        lines.append("- Job looks healthy — keep the same recipe for the next slug.")
    lines.append("")

    return "\n".join(lines) + "\n"


# ----------------------------------------------------------------------------
# Workflow state patching
# ----------------------------------------------------------------------------


def patch_workflow_state(
    slug: str,
    retro_path: Path,
    lessons: list[str],
    update_state: bool,
) -> dict[str, Any]:
    state = load_workflow_state(slug) or {"slug": slug}
    state.setdefault("retrospective_path", str(retro_path.relative_to(retro_path.parents[2])))
    state["lessons_learned"] = lessons
    state.setdefault("alerts", [])
    if update_state:
        save_workflow_state(slug, state)
    return state


# ----------------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------------


def cmd_generate(args: argparse.Namespace) -> int:
    if args.slug == "__all__":
        slugs = list_workflow_slugs()
        if not slugs:
            print("[WARN] no workflow states found")
            return 0
        for slug in slugs:
            args.slug = slug
            cmd_generate(args)
        return 0

    validate_slug(args.slug)
    workflow = load_workflow_state(args.slug)
    if workflow is None:
        print(f"[BLOCKED] workflow state not found for slug: {args.slug}")
        return 1

    risp_entries = risp_entries_for_slug(args.slug)
    image_plan = load_image_plan(args.slug)
    outcomes = telegram_outcomes(workflow)
    body = render_markdown(args.slug, workflow, risp_entries, image_plan, outcomes)

    out_dir = RETRO_DIR / ymd(_safe_created_date(workflow))
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{args.slug}.md"
    out_path.write_text(body, encoding="utf-8")
    print(f"[OK] retrospective written: {out_path}")

    lessons = extract_lessons(workflow, risp_entries, image_plan, outcomes)
    if args.update_state:
        patch_workflow_state(args.slug, out_path, lessons, update_state=True)
        print(f"[OK] workflow state updated: {WORKFLOW_DIR / f'{args.slug}.json'}")
    else:
        # Always store the path on the in-memory copy for the JSON sidecar,
        # but only persist when --update-state is passed.
        state = patch_workflow_state(args.slug, out_path, lessons, update_state=False)
        if "lessons_learned" in state:
            sidecar = out_dir / f"{args.slug}.json"
            sidecar.write_text(
                json.dumps(
                    {
                        "slug": args.slug,
                        "retrospective_path": str(out_path),
                        "lessons_learned": lessons,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            print(f"[OK] sidecar written: {sidecar}")
    return 0


def _safe_created_date(workflow: dict[str, Any]):
    """Return the date for the retrospective folder based on the workflow's created_at."""
    from datetime import datetime as _dt
    from feedback.lib import KST, parse_iso_kst

    created = workflow.get("created_at")
    if not created:
        return _dt.now(KST)
    parsed = parse_iso_kst(created)
    return parsed or _dt.now(KST)


def cmd_stats(args: argparse.Namespace) -> int:
    from feedback.lib import parse_since, load_risp_progress

    window_start = parse_since(args.since)
    slugs = list_workflow_slugs()
    items: list[dict[str, Any]] = []
    for slug in slugs:
        workflow = load_workflow_state(slug)
        if not workflow:
            continue
        created = workflow.get("created_at")
        from feedback.lib import parse_iso_kst

        parsed = parse_iso_kst(created) if created else None
        if parsed and parsed < window_start:
            continue
        lessons = workflow.get("lessons_learned") or []
        items.append(
            {
                "slug": slug,
                "status": workflow.get("status", "UNKNOWN"),
                "created_at": created,
                "lessons_count": len(lessons),
            }
        )
    items.sort(key=lambda d: d.get("created_at") or "", reverse=True)
    summary = {
        "window": args.since,
        "window_start": window_start.isoformat(timespec="seconds"),
        "workflow_count": len(items),
        "items": items,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a per-job retrospective markdown report.")
    sub = parser.add_subparsers(dest="command", required=True)

    g = sub.add_parser("generate", help="Generate retrospective for one slug or all")
    g.add_argument("--slug", required=True, help="Slug or the literal '__all__'")
    g.add_argument(
        "--update-state",
        action="store_true",
        help="Patch data/workflow-runs/{slug}.json with retrospective_path + lessons_learned",
    )
    g.set_defaults(func=cmd_generate)

    s = sub.add_parser("stats", help="Show retrospective stats over a time window")
    s.add_argument(
        "--since",
        default="7d",
        help="Window like 7d, 24h, 4w (default: 7d)",
    )
    s.set_defaults(func=cmd_stats)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
