#!/usr/bin/env python3
"""v3 SNS 병렬 게시 — Threads 먼저 → IG + FB 동시.

순서:
  1) Threads (이미지 처리 때문에 먼저)
  2) Instagram + Facebook 동시 (서로 무관)
  3) 모든 결과 수집 후 통합 보고

사용법:
    python3 parallel_sns_publish.py \\
        --blog-url "https://techllm.github.io/posts/foo/" \\
        --title "..." \\
        --threads-image "https://.../threads-comic.png" \\
        --ig-images "url1,url2,url3,url4,url5" \\
        --ig-caption "..." \\
        --fb-image "https://.../cover.png" \\
        --fb-summary "..." \\
        --tags "ai,llm,techllm" \\
        --dry-run
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

KST = timezone(timedelta(hours=9))

HOME = Path.home()
THREADS_SCRIPT = os.getenv(
    "THREADS_PUBLISHER_SCRIPT",
    str(HOME / ".openclaw/skills/threads-toolkit-skill/scripts/post_threads.py"),
)
IG_SCRIPT = os.getenv(
    "INSTAGRAM_PUBLISHER_SCRIPT",
    str(HOME / ".openclaw/workspace-blogger/skills/instagram-cardnews/post.py"),
)
FB_SCRIPT = os.getenv(
    "FACEBOOK_PUBLISHER_SCRIPT",
    str(HOME / ".openclaw/workspace-blogger/skills/facebook-publisher/post.py"),
)
ENV_FILE = os.getenv("OPENCLAW_ENV_FILE", str(HOME / ".openclaw/.env"))
PYTHON = os.getenv("PYTHON_BIN", sys.executable)


def now_kst() -> str:
    return datetime.now(KST).isoformat(timespec="seconds")


def post_threads(blog_url: str, title: str, image_url: str, posts: list[str], dry_run: bool) -> dict[str, Any]:
    """Threads 3부작 게시."""
    if dry_run:
        return {
            "channel": "threads",
            "status": "ok",
            "stdout": f"[DRY RUN] {title} / {blog_url} / image={image_url} / posts={len(posts)}",
            "stderr": "",
            "returncode": 0,
        }

    cmd = [
        PYTHON, THREADS_SCRIPT,
        "--env", ENV_FILE,
        "--image-url", image_url,
        "--title", title,
        "--blog-url", blog_url,
    ]
    if not dry_run:
        cmd.append("--rehost-image")
    for p in posts:
        cmd += ["--post", p]
    if dry_run:
        cmd.append("--dry-run")
    print("[Threads] post_threads.py 호출 준비...")
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        return {
            "channel": "threads",
            "status": "ok" if r.returncode == 0 else "fail",
            "stdout": r.stdout[-500:],
            "stderr": r.stderr[-500:],
            "returncode": r.returncode,
        }
    except subprocess.TimeoutExpired:
        return {"channel": "threads", "status": "fail", "stderr": "timeout 120s"}


def post_instagram_full(
    images: list[str],
    caption: str,
    title: str,
    blog_url: str,
    summary: str,
    tags: list[str],
    dry_run: bool,
) -> dict[str, Any]:
    """Instagram 카드뉴스 5장 게시 (로그 메타데이터 포함)."""
    cmd = [
        PYTHON, IG_SCRIPT,
        "--images", ",".join(images),
        "--caption", caption,
        "--title", title,
        "--url", blog_url,
        "--summary", summary,
        "--tags", ",".join(tags),
    ]
    if dry_run:
        cmd.append("--dry-run")
    print(f"[Instagram] {len(images)}장...")
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        return {
            "channel": "instagram",
            "status": "ok" if r.returncode == 0 else "fail",
            "stdout": r.stdout[-500:],
            "stderr": r.stderr[-500:],
            "returncode": r.returncode,
        }
    except subprocess.TimeoutExpired:
        return {"channel": "instagram", "status": "fail", "stderr": "timeout 120s"}


def post_facebook(blog_url: str, title: str, image_url: str, summary: str, tags: list[str], dry_run: bool) -> dict[str, Any]:
    """Facebook 사진 포스트."""
    cmd = [
        PYTHON, FB_SCRIPT,
        "--title", title,
        "--url", blog_url,
        "--image", image_url,
        "--summary", summary,
        "--tags", ",".join(tags),
    ]
    if dry_run:
        cmd.append("--dry-run")
    print(f"[Facebook] {title[:30]}...")
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        return {
            "channel": "facebook",
            "status": "ok" if r.returncode == 0 else "fail",
            "stdout": r.stdout[-500:],
            "stderr": r.stderr[-500:],
            "returncode": r.returncode,
        }
    except subprocess.TimeoutExpired:
        return {"channel": "facebook", "status": "fail", "stderr": "timeout 120s"}


def main() -> int:
    parser = argparse.ArgumentParser(description="v3 SNS 병렬 게시 (Threads → IG+FB 동시)")
    parser.add_argument("--blog-url", required=True)
    parser.add_argument("--title", required=True)
    parser.add_argument("--threads-image", required=True, help="Threads 4컷 만화 URL (1:1)")
    parser.add_argument("--threads-posts", nargs="+", required=True, help="3부작 텍스트")
    parser.add_argument("--ig-images", required=True, help="5장 콤마구분")
    parser.add_argument("--ig-caption", required=True)
    parser.add_argument("--fb-image", required=True)
    parser.add_argument("--fb-summary", required=True)
    parser.add_argument("--tags", default="ai,llm,techllm")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    print("=" * 60)
    print("# v3 SNS 병렬 게시")
    print(f"  블로그: {args.blog_url}")
    print(f"  제목:   {args.title}")
    print(f"  모드:   {'DRY-RUN' if args.dry_run else 'LIVE'}")
    print("=" * 60)
    print()

    results: list[dict[str, Any]] = []

    # Step 1: Threads 먼저
    print("[1/2] Threads 단독 게시...")
    results.append(post_threads(args.blog_url, args.title, args.threads_image, args.threads_posts, args.dry_run))
    print(f"  → {results[-1]['status']}")
    print()

    # Step 2: IG + FB 동시
    print("[2/2] Instagram + Facebook 동시 게시...")
    ig_images = args.ig_images.split(",")
    tags = args.tags.split(",")
    with ThreadPoolExecutor(max_workers=2) as ex:
        fut_ig = ex.submit(
            post_instagram_full,
            ig_images,
            args.ig_caption,
            args.title,
            args.blog_url,
            args.fb_summary,
            tags,
            args.dry_run,
        )
        fut_fb = ex.submit(post_facebook, args.blog_url, args.title, args.fb_image, args.fb_summary, tags, args.dry_run)
        for fut in as_completed([fut_ig, fut_fb]):
            r = fut.result()
            results.append(r)
            print(f"  → {r['channel']}: {r['status']}")

    # 결과 통합 보고
    print()
    print("=" * 60)
    print("# 결과")
    print("=" * 60)
    for r in results:
        emoji = "✅" if r["status"] == "ok" else "❌"
        print(f"{emoji} {r['channel']:10s} {r['status']}")
        if r["status"] != "ok" and r.get("stderr"):
            print(f"   stderr: {r['stderr'][:200]}")

    # 로그 저장
    log_path = Path("data/sns_v3_runs.jsonl")
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as f:
        for r in results:
            f.write(
                json.dumps(
                    {
                        "timestamp": now_kst(),
                        "blog_url": args.blog_url,
                        "title": args.title,
                        "mode": "dry-run" if args.dry_run else "live",
                        **r,
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )

    failed = [r["channel"] for r in results if r["status"] != "ok"]
    if failed:
        print(f"\n❌ 실패 채널: {', '.join(failed)}")
        return 1
    print("\n✅ 3채널 모두 완료")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
