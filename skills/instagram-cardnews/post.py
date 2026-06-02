#!/usr/bin/env python3
"""Instagram carousel publisher wrapper used by the unified SNS pipeline."""

from __future__ import annotations

import argparse
import sys

from generate_cards import load_env, log_publish, post_carousel, post_single_image


def main() -> int:
    parser = argparse.ArgumentParser(description="Instagram 카드뉴스 발행 wrapper")
    parser.add_argument("--images", required=True, help="이미지 URL 목록 (쉼표 구분, 기본 2~10장)")
    parser.add_argument("--caption", required=True, help="완성된 Instagram 캡션")
    parser.add_argument("--title", default="", help="로그용 블로그 제목")
    parser.add_argument("--url", default="", help="로그용 블로그 URL")
    parser.add_argument("--summary", default="", help="로그/미리보기용 요약")
    parser.add_argument("--tags", default="", help="로그/미리보기용 태그")
    parser.add_argument("--single", action="store_true", help="단일 이미지 발행 허용")
    parser.add_argument("--dry-run", action="store_true", help="실제 발행 안 함")
    args = parser.parse_args()

    image_urls = [u.strip() for u in args.images.split(",") if u.strip()]
    if not image_urls:
        print("ERROR: --images URL 목록이 필요합니다.", file=sys.stderr)
        return 1
    if len(image_urls) == 1 and not args.single:
        print("ERROR: Instagram 카드뉴스 기본값은 캐러셀입니다. 2~10장 공급 또는 --single 사용.", file=sys.stderr)
        return 2
    if len(image_urls) > 10:
        print("WARNING: Instagram 캐러셀 최대 10장. 처음 10장만 사용합니다.")
        image_urls = image_urls[:10]

    print("=" * 50)
    print("Instagram 카드뉴스 미리보기")
    print("=" * 50)
    print("계정: configured Instagram Business account")
    print(f"슬라이드 수: {len(image_urls)}장")
    if args.title:
        print(f"제목: {args.title}")
    if args.url:
        print(f"블로그 URL: {args.url}")
    print(f"\n[캡션]\n{args.caption}")
    print("\n[이미지 목록]")
    for i, url in enumerate(image_urls, start=1):
        print(f"  슬라이드 {i}: {url[:100]}...")
    print("=" * 50)

    if args.dry_run:
        print("OK: [DRY RUN] 실제 발행 안 함")
        return 0

    env = load_env()
    token = env.get("META_GRAPH_TOKEN", "")
    ig_id = env.get("INSTAGRAM_BUSINESS_ACCOUNT_ID", "")
    if not token:
        print("ERROR: META_GRAPH_TOKEN이 .env에 없습니다.", file=sys.stderr)
        return 1
    if not ig_id:
        print("ERROR: INSTAGRAM_BUSINESS_ACCOUNT_ID가 .env에 없습니다.", file=sys.stderr)
        return 1

    if len(image_urls) == 1:
        post_id, err = post_single_image(ig_id, token, image_urls[0], args.caption)
    else:
        post_id, err = post_carousel(ig_id, token, image_urls, args.caption, media_type="image")

    if not post_id:
        print(f"ERROR: Instagram 발행 실패: {err}", file=sys.stderr)
        return 1

    post_url = f"https://www.instagram.com/p/{post_id}/"
    print("OK: Instagram 발행 성공")
    print(f"Post ID: {post_id}")
    print(f"URL: {post_url}")
    log_publish(
        "instagram",
        post_id,
        url=post_url,
        title=args.title,
        blog_url=args.url,
        image_url=image_urls[0],
        extra={"slide_count": len(image_urls), "summary": args.summary, "tags": args.tags},
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
