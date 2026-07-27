#!/usr/bin/env python3
"""Dry-run checker for Threads SNS approval logs.

This script does not call Meta APIs and never posts externally.
It validates whether a selected Threads draft is ready for posting.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

THREADS_TEXT_LIMIT = 500


def count_chars(text: str) -> int:
    """Count Python unicode code points as a practical preflight check."""
    return len(text or "")


def load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise SystemExit(f"[ERROR] Approval log not found: {path}")
    except json.JSONDecodeError as exc:
        raise SystemExit(f"[ERROR] Invalid JSON: {path}\n{exc}")


def validate(log: dict) -> tuple[bool, list[str], dict]:
    errors: list[str] = []
    warnings: list[str] = []

    approval_id = log.get("approval_id", "")
    status = log.get("status", "")
    blog = log.get("blog", {}) or {}
    platforms = log.get("platforms", {}) or {}
    threads = platforms.get("threads", {}) or {}

    # 3단 스레드(posts 배열)와 단일 content를 모두 인정한다. posts만 있는 로그를
    # "content is empty"로 막던 것이 Threads 게시 실패의 실제 원인이었다.
    content = str(threads.get("content") or threads.get("selected_content") or "").strip()
    if not content:
        content = "\n\n".join(
            str((post or {}).get("content") or "").strip()
            for post in (threads.get("posts") or [])
            if isinstance(post, dict) and str((post or {}).get("content") or "").strip()
        ).strip()
    char_count = count_chars(content)
    published_url = blog.get("published_url", "") or ""

    if not approval_id:
        errors.append("approval_id is missing")

    if status not in {"pending_review", "approved", "posted"}:
        warnings.append(f"overall status is '{status}', expected pending_review/approved/posted for review")

    if not threads.get("enabled", False):
        errors.append("Threads platform is not enabled")

    if not content.strip():
        errors.append("Threads content is empty")

    if char_count > THREADS_TEXT_LIMIT:
        errors.append(f"Threads content exceeds {THREADS_TEXT_LIMIT} characters: {char_count}")

    if published_url and published_url not in content:
        warnings.append("published_url is not included in Threads content")

    if threads.get("status") == "posted":
        warnings.append("Threads status is already posted")

    meta = {
        "approval_id": approval_id,
        "blog_title": blog.get("title", ""),
        "blog_url": published_url,
        "overall_status": status,
        "threads_status": threads.get("status", ""),
        "selected_variant": threads.get("selected_variant", ""),
        "character_count": char_count,
        "within_limit": char_count <= THREADS_TEXT_LIMIT,
        "warnings": warnings,
    }

    return not errors, errors, meta


def main() -> int:
    parser = argparse.ArgumentParser(description="Dry-run validate a Threads SNS approval log.")
    parser.add_argument("approval_log", type=Path, help="Path to approval log JSON")
    parser.add_argument("--show-content", action="store_true", help="Print selected Threads content")
    args = parser.parse_args()

    log = load_json(args.approval_log)
    ok, errors, meta = validate(log)

    print("# Threads Dry Run")
    print(f"approval_id: {meta['approval_id']}")
    print(f"blog_title: {meta['blog_title']}")
    print(f"blog_url: {meta['blog_url']}")
    print(f"overall_status: {meta['overall_status']}")
    print(f"threads_status: {meta['threads_status']}")
    print(f"selected_variant: {meta['selected_variant']}")
    print(f"character_count: {meta['character_count']} / {THREADS_TEXT_LIMIT}")
    print(f"within_limit: {str(meta['within_limit']).lower()}")

    if meta["warnings"]:
        print("\nWarnings:")
        for warning in meta["warnings"]:
            print(f"- {warning}")

    if errors:
        print("\nErrors:")
        for error in errors:
            print(f"- {error}")

    if args.show_content:
        content = (((log.get("platforms") or {}).get("threads") or {}).get("content") or "")
        print("\n--- Threads Content ---")
        print(content)

    print(f"\nresult: {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
