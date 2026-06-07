#!/usr/bin/env python3
"""Top-level harness helper for blog + SNS jobs.

The harness is intentionally a state/checkpoint layer, not a public publisher.
It initializes the workflow guard and image plan together, records text-review
passes, and provides one status command that makes incomplete stages obvious.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path


WORKSPACE = Path("/Users/noah/.openclaw/workspace-blogger")
PYTHON = "/opt/homebrew/bin/python3"
GUARD = WORKSPACE / "scripts" / "blog_workflow_guard.py"
IMAGE_RUNNER = WORKSPACE / "scripts" / "sns" / "image_resume_runner.py"


def run(cmd: list[str]) -> int:
    result = subprocess.run(cmd, cwd=WORKSPACE)
    return result.returncode


def cmd_init(args: argparse.Namespace) -> int:
    guard_cmd = [
        PYTHON,
        str(GUARD),
        "init",
        "--slug",
        args.slug,
        "--title",
        args.title,
        "--source-url",
        args.source_url,
        "--style",
        args.style,
        "--mode",
        args.mode,
        "--harness-intensity",
        args.intensity,
    ]
    image_cmd = [
        PYTHON,
        str(IMAGE_RUNNER),
        "init",
        "--slug",
        args.slug,
        "--title",
        args.title,
        "--style",
        args.style,
        "--profile",
        args.image_profile,
    ]
    if args.force:
        guard_cmd.append("--force")
        image_cmd.append("--force")
    guard_code = run(guard_cmd)
    if guard_code != 0:
        return guard_code
    image_code = run(image_cmd)
    if image_code != 0:
        return image_code
    print("[OK] blog+SNS harness initialized")
    return 0


def cmd_record_text_review(args: argparse.Namespace) -> int:
    # 1) text review 기록
    cmd = [
        PYTHON,
        str(GUARD),
        "update",
        "--slug",
        args.slug,
        "--status",
        "TEXT_REVIEWED",
        "--minimax",
        "done",
        "--minimax-revisions",
        str(args.minimax_revisions),
        "--humanize-korean",
        "done",
        "--poetry-rhythm",
        "done",
        "--harness-status",
        "text_reviewed",
    ]
    if args.claude:
        cmd.extend(["--claude", args.claude])
    if args.gpt_fallback:
        cmd.extend(["--gpt-fallback", args.gpt_fallback])
    if args.note:
        cmd.extend(["--note", args.note])
    rc = run(cmd)
    if rc != 0:
        return rc

    # 2) Track-A 2026-06-07: audit --stage draft를 자동 실행해서
    #    본문 + image plan skeleton이 draft 기준을 만족하는지 검증.
    #    사용자가 "초안 끝났다"고 말한 직후 즉시 fail을 잡아내기 위함.
    if not args.skip_audit:
        audit_cmd = [
            PYTHON,
            str(GUARD),
            "audit",
            "--slug",
            args.slug,
            "--stage",
            "draft",
        ]
        audit_rc = run(audit_cmd)
        if audit_rc != 0:
            print(
                f"[WARN] draft audit failed (rc={audit_rc}). "
                f"블로그 워크플로우 가드가 blocked_reason을 기록하고 "
                f"텔레그램으로 알림을 발송했습니다. "
                f"`python3 scripts/blog_workflow_guard.py status --slug {args.slug}` "
                f"또는 `python3 scripts/blog_sns_harness.py status --slug {args.slug} --verbose` "
                f"로 차단 사유를 확인하세요.",
                file=sys.stderr,
            )
            return audit_rc
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    state_path = WORKSPACE / "data" / "workflow-runs" / f"{args.slug}.json"
    image_path = WORKSPACE / "data" / "image-plans" / f"{args.slug}.json"
    payload = {
        "workflow_state_exists": state_path.exists(),
        "image_plan_exists": image_path.exists(),
        "workflow_state": json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else None,
        "image_plan_summary": None,
    }
    if image_path.exists():
        plan = json.loads(image_path.read_text(encoding="utf-8"))
        assets = plan.get("assets", [])
        payload["image_plan_summary"] = {
            "asset_count": len(assets),
            "ready_count": len([a for a in assets if a.get("status") in {"copied", "reviewed", "approved"}]),
            "reviewed_count": len([a for a in assets if a.get("status") in {"reviewed", "approved"}]),
            "pending": [a.get("id") for a in assets if a.get("status") not in {"copied", "reviewed", "approved"}],
        }

    # Track-A 2026-06-07: --verbose는 사용자가 "왜 멈춰있지?" 물을 때 즉시
    # blocker reason과 stale 여부를 보여준다. 형님/Harness가 이걸 텔레그램
    # 답변에 그대로 인용할 수 있도록 human-readable 필드를 함께 출력.
    if args.verbose:
        verbose = {}
        if state_path.exists():
            state = payload["workflow_state"] or {}
            verbose["status"] = state.get("status")
            verbose["blocked_reason"] = state.get("blocked_reason")
            verbose["updated_at"] = state.get("updated_at")
            # Track-A: stale 계산 (30분)
            updated_at = state.get("updated_at")
            if updated_at:
                KST = timezone(timedelta(hours=9))
                try:
                    ts = datetime.fromisoformat(updated_at)
                    if ts.tzinfo is None:
                        ts = ts.replace(tzinfo=KST)
                    age_minutes = (datetime.now(KST) - ts).total_seconds() / 60
                    verbose["age_minutes"] = round(age_minutes, 1)
                    verbose["stale"] = age_minutes > 30
                except Exception:
                    pass
            # last 3 notes
            notes = state.get("notes") or []
            verbose["recent_notes"] = notes[-3:]
            review = state.get("review") or {}
            verbose["review"] = review
        payload["verbose"] = verbose

        if state_path.exists() and not image_path.exists():
            print(
                f"[HINT] image plan이 없습니다. `scripts/sns/image_resume_runner.py init --slug {args.slug}` 으로 생성하세요.",
                file=sys.stderr,
            )

    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Harness entrypoint for blog+SNS jobs")
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init")
    init.add_argument("--slug", required=True)
    init.add_argument("--title", required=True)
    init.add_argument("--source-url", required=True)
    init.add_argument("--style", choices=["hand-drawing", "oil"], default="hand-drawing")
    init.add_argument("--mode", choices=["blog", "sns", "blog-sns"], default="blog-sns")
    init.add_argument("--intensity", choices=["strong", "medium", "light"], default="strong")
    init.add_argument("--image-profile", choices=["default", "minimax-only"], default="default")
    init.add_argument("--force", action="store_true")
    init.set_defaults(func=cmd_init)

    text_review = sub.add_parser("record-text-review")
    text_review.add_argument("--slug", required=True)
    text_review.add_argument("--minimax-revisions", type=int, default=2)
    text_review.add_argument("--claude", choices=["pending", "done", "failed", "skipped"])
    text_review.add_argument("--gpt-fallback", choices=["pending", "done", "not_needed", "failed"])
    text_review.add_argument("--note")
    text_review.add_argument(
        "--skip-audit",
        action="store_true",
        help="Track-A 2026-06-07: 자동 audit --stage draft 실행을 건너뜁니다. 기본값은 실행.",
    )
    text_review.set_defaults(func=cmd_record_text_review)

    status = sub.add_parser("status")
    status.add_argument("--slug", required=True)
    status.add_argument(
        "--verbose",
        action="store_true",
        help="Track-A 2026-06-07: blocker_reason, updated_at, stale 여부, 마지막 note, review 상태를 함께 표시합니다.",
    )
    status.set_defaults(func=cmd_status)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
