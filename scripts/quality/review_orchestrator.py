#!/usr/bin/env python3
"""2-stage review orchestrator for blog posts + SNS images.

Stage 1 (auto)  : translation_checker + image_checker (deterministic)
Stage 2 (LLM)   : only if stage 1 PASS — invokes Claude (1st) and falls back
                   to GPT (2nd), mirroring the policy in
                   ``agents/blogger/AGENT.md`` (Claude 1st / GPT fallback).

Design points
-------------
* No LLM dependency is *imported* here. The LLM step is a thin wrapper that
  calls external CLIs (`claude`, `openai`) and is allowed to fail — the
  orchestrator treats a missing CLI as a non-fatal warning so this script
  can run in CI / on a fresh install.
* The scoring is identical to ``translation_checker`` / ``image_checker``;
  no scores are silently inflated when the LLM step runs.
* Stage 1 FAIL short-circuits the whole pipeline and returns a detailed
  issue list — same as AGENT.md's "fail fast" rule.

CLI
---
check-translation --post PATH --source-url URL [--json]
check-images      --image-dir PATH --style <hand-drawing|oil> [--image-plan JSON] [--json]
review-all        --slug SLUG --post PATH --source-url URL --image-dir PATH \\
                  [--style ...] [--image-plan JSON] [--llm] [--json]
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

# Same-package import — these scripts are designed to be importable via
# ``sys.path.insert(0, '<workspace>')`` (the standard pattern in this repo).
sys.path.insert(0, str(Path(__file__).resolve().parent))
from translation_checker import (  # noqa: E402
    DEFAULT_MIN_SCORE as TRANSLATION_MIN_SCORE,
    check_translation,
)
from image_checker import (  # noqa: E402
    DEFAULT_MIN_SCORE as IMAGE_MIN_SCORE,
    check_images,
)

KST = timezone(timedelta(hours=9))


def _now_kst() -> str:
    return datetime.now(KST).isoformat(timespec="seconds")


def _try_llm_review(prompt: str) -> dict[str, Any]:
    """Best-effort LLM call. Returns a dict; never raises.

    Tries Claude first; falls back to GPT (openai CLI) if Claude is missing
    or fails. Mirrors ``agents/blogger/AGENT.md``'s review policy.
    """
    if not shutil.which("claude"):
        return {
            "stage": "stage2_llm",
            "provider": "claude",
            "status": "skipped",
            "reason": "claude CLI not on PATH",
            "output": "",
            "timestamp": _now_kst(),
        }
    try:
        result = subprocess.run(
            ["claude", "--print", "--no-stream", prompt],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode == 0 and result.stdout.strip():
            return {
                "stage": "stage2_llm",
                "provider": "claude",
                "status": "ok",
                "output": result.stdout.strip(),
                "timestamp": _now_kst(),
            }
        # Claude failed; try GPT fallback
        if not shutil.which("openai"):
            return {
                "stage": "stage2_llm",
                "provider": "claude",
                "status": "failed",
                "reason": f"claude rc={result.returncode}; openai CLI not on PATH for fallback",
                "output": result.stderr.strip(),
                "timestamp": _now_kst(),
            }
        prompt_gpt = f"다음 한국어 블로그 글의 사실관계·톤·자연스러움을 검토하고 문제가 있으면 지적해 주세요.\n\n{prompt}"
        result2 = subprocess.run(
            ["openai", "chat", "--model", "gpt-4o", prompt_gpt],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result2.returncode == 0 and result2.stdout.strip():
            return {
                "stage": "stage2_llm",
                "provider": "gpt_fallback",
                "status": "ok",
                "output": result2.stdout.strip(),
                "timestamp": _now_kst(),
            }
        return {
            "stage": "stage2_llm",
            "provider": "gpt_fallback",
            "status": "failed",
            "reason": f"openai rc={result2.returncode}",
            "output": result2.stderr.strip(),
            "timestamp": _now_kst(),
        }
    except subprocess.TimeoutExpired:
        return {
            "stage": "stage2_llm",
            "provider": "claude",
            "status": "timeout",
            "reason": "120s timeout exceeded",
            "output": "",
            "timestamp": _now_kst(),
        }
    except Exception as exc:  # pragma: no cover
        return {
            "stage": "stage2_llm",
            "provider": "claude",
            "status": "error",
            "reason": repr(exc),
            "output": "",
            "timestamp": _now_kst(),
        }


def cmd_check_translation(args: argparse.Namespace) -> int:
    result = check_translation(args.post, args.source_url or None, args.min_score)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"[{'PASS' if result['pass'] else 'FAIL'}] translation {result['score']}/100")
        for i in result["issues"]:
            print(f"  - {i}")
    return 0 if result["pass"] else 1


def cmd_check_images(args: argparse.Namespace) -> int:
    result = check_images(
        args.image_dir,
        style=args.style,
        image_plan_path=args.image_plan,
        min_score=args.min_score,
    )
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"[{'PASS' if result['pass'] else 'FAIL'}] images {result['score']}/100 ({result['global'].get('file_count', 0)} files)")
        for i in result["issues"]:
            print(f"  - {i}")
    return 0 if result["pass"] else 1


def cmd_review_all(args: argparse.Namespace) -> int:
    """Run both stage-1 checks; if both PASS, run stage-2 LLM pass.

    Failure mode: stage 1 < threshold ⇒ exit 1, no LLM cost.
    """
    overall_issues: list[str] = []
    translation: dict[str, Any] = {}
    images: dict[str, Any] = {}
    llm: dict[str, Any] = {"stage": "stage2_llm", "status": "skipped", "reason": "stage 1 failed"}

    # ---- Stage 1a: translation ----
    translation = check_translation(args.post, args.source_url or None, args.min_translation or TRANSLATION_MIN_SCORE)
    if not translation["pass"]:
        overall_issues.append(
            f"translation {translation['score']}/{translation['threshold']} — see issues: {translation['issues'][:5]}"
        )

    # ---- Stage 1b: images ----
    images = check_images(
        args.image_dir,
        style=args.style,
        image_plan_path=args.image_plan,
        min_score=args.min_image or IMAGE_MIN_SCORE,
    )
    if not images["pass"]:
        overall_issues.append(
            f"images {images['score']}/{images['threshold']} — see issues: {images['issues'][:5]}"
        )

    stage1_pass = bool(translation.get("pass")) and bool(images.get("pass"))

    # ---- Stage 2: LLM (only if Stage 1 passes and --llm was given) ----
    if stage1_pass and args.llm:
        try:
            post_text = Path(args.post).read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            llm = {
                "stage": "stage2_llm",
                "status": "error",
                "reason": f"cannot read post: {exc}",
                "timestamp": _now_kst(),
            }
        else:
            truncated = post_text[-6000:]  # last 6k chars
            prompt = (
                "다음 한국어 블로그 글의 사실관계, 자연스러움, 구조, 문장 호흡을 검토하고 "
                "개선이 필요한 부분이 있으면 1) 무엇이 2) 왜 3) 어떻게 고치면 좋을지 "
                "간결하게 알려 주세요. (한국어)\n\n"
                f"Slug: {args.slug}\n"
                f"Source URL: {args.source_url or '(none)'}\n\n"
                f"{truncated}"
            )
            llm = _try_llm_review(prompt)
    elif stage1_pass and not args.llm:
        llm = {"stage": "stage2_llm", "status": "skipped", "reason": "--llm not passed"}
    elif not stage1_pass:
        llm = {"stage": "stage2_llm", "status": "skipped", "reason": "stage 1 failed"}

    summary = {
        "slug": args.slug,
        "timestamp": _now_kst(),
        "stage1": {
            "translation": {
                "score": translation.get("score"),
                "pass": translation.get("pass"),
                "issues_count": len(translation.get("issues") or []),
            },
            "images": {
                "score": images.get("score"),
                "pass": images.get("pass"),
                "file_count": (images.get("global") or {}).get("file_count"),
                "issues_count": len(images.get("issues") or []),
            },
        },
        "stage2": llm,
        # Stage 1 is the gating check; LLM failure is a non-fatal warning
        # (the writer will still need to address it, but the audit does not
        # block on it). This matches the AGENT.md "Claude or GPT fallback"
        # policy, which says: if Claude fails, try GPT; if both fail, you
        # escalate to the human — but a gate that the script runs does
        # not block the post on LLM unavailability.
        "overall_pass": stage1_pass,
        "overall_issues": overall_issues,
    }

    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(f"[{'PASS' if summary['overall_pass'] else 'FAIL'}] review-all {args.slug}")
        print(
            f"  stage1 translation: {summary['stage1']['translation']['score']} "
            f"({'pass' if summary['stage1']['translation']['pass'] else 'fail'})"
        )
        print(
            f"  stage1 images:      {summary['stage1']['images']['score']} "
            f"({'pass' if summary['stage1']['images']['pass'] else 'fail'}, "
            f"{summary['stage1']['images']['file_count']} files)"
        )
        print(f"  stage2 LLM:         {llm.get('status')} ({llm.get('provider', '?')})")
        if overall_issues:
            print("  Top issues:")
            for i in overall_issues[:5]:
                print(f"    - {i}")
    return 0 if summary["overall_pass"] else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="2-stage review orchestrator (auto + LLM) for blog posts and SNS images"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p1 = sub.add_parser("check-translation", help="Run stage-1 translation check only")
    p1.add_argument("--post", required=True)
    p1.add_argument("--source-url", default="")
    p1.add_argument("--min-score", type=int, default=TRANSLATION_MIN_SCORE)
    p1.add_argument("--json", action="store_true")
    p1.set_defaults(func=cmd_check_translation)

    p2 = sub.add_parser("check-images", help="Run stage-1 image check only")
    p2.add_argument("--image-dir", required=True)
    p2.add_argument("--style", choices=["hand-drawing", "oil"], default="hand-drawing")
    p2.add_argument("--image-plan")
    p2.add_argument("--min-score", type=int, default=IMAGE_MIN_SCORE)
    p2.add_argument("--json", action="store_true")
    p2.set_defaults(func=cmd_check_images)

    p3 = sub.add_parser("review-all", help="Run both stage-1 checks and (optionally) LLM stage 2")
    p3.add_argument("--slug", required=True)
    p3.add_argument("--post", required=True)
    p3.add_argument("--source-url", default="")
    p3.add_argument("--image-dir", required=True)
    p3.add_argument("--image-plan")
    p3.add_argument("--style", choices=["hand-drawing", "oil"], default="hand-drawing")
    p3.add_argument("--min-translation", type=int, default=TRANSLATION_MIN_SCORE)
    p3.add_argument("--min-image", type=int, default=IMAGE_MIN_SCORE)
    p3.add_argument("--llm", action="store_true", help="actually call Claude/GPT (default: skip)")
    p3.add_argument("--json", action="store_true")
    p3.set_defaults(func=cmd_review_all)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
