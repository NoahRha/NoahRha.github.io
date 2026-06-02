#!/usr/bin/env python3
"""블로그 글 → Instagram 카드뉴스(캐러셀) 자동 포스팅"""

import os
import sys
import json
import argparse
import time
import urllib.request
import urllib.parse
from pathlib import Path


SNS_LOG_PATH = Path(
    os.getenv(
        "SNS_PUBLISH_LOG_PATH",
        str(Path.home() / ".openclaw/workspace-blogger/data/sns_publish_log.jsonl"),
    )
)


def log_publish(channel, post_id, *, url='', title='', blog_url='', image_url='', extra=None):
    import datetime as _dt
    entry = {
        'timestamp': _dt.datetime.now(_dt.timezone.utc).astimezone().isoformat(timespec='seconds'),
        'channel': channel,
        'post_id': post_id,
        'url': url,
        'title': title,
        'blog_url': blog_url,
        'image_url': image_url,
    }
    if extra:
        entry['extra'] = extra
    try:
        SNS_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with SNS_LOG_PATH.open('a', encoding='utf-8') as f:
            f.write(json.dumps(entry, ensure_ascii=False) + '\n')
    except OSError as exc:
        print(f'WARN: sns_publish_log append failed: {exc}', file=sys.stderr)


def load_env():
    env_path = os.path.expanduser(os.getenv("OPENCLAW_ENV_FILE", "~/.openclaw/.env"))
    env = {}
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    env[k.strip()] = v.strip()
    return env


def api_post(url, data: dict):
    payload = urllib.parse.urlencode(data).encode()
    req = urllib.request.Request(url, data=payload, method="POST")
    try:
        with urllib.request.urlopen(req) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return json.loads(e.read())


def create_image_container(ig_id, token, image_url, is_carousel_item=True):
    """개별 이미지 컨테이너 생성"""
    data = {
        "image_url": image_url,
        "is_carousel_item": "true" if is_carousel_item else "false",
        "access_token": token,
    }
    result = api_post(f"https://graph.facebook.com/v21.0/{ig_id}/media", data)
    return result.get("id")


def create_video_container(ig_id, token, video_url, is_carousel_item=True):
    """개별 비디오 컨테이너 생성 (REELS-style 5초 MP4 슬라이드용)"""
    data = {
        "media_type": "VIDEO",
        "video_url": video_url,
        "is_carousel_item": "true" if is_carousel_item else "false",
        "access_token": token,
    }
    result = api_post(f"https://graph.facebook.com/v21.0/{ig_id}/media", data)
    return result.get("id")


def poll_container_status(token, container_id, max_seconds=120, interval=4):
    """비디오/카드 컨테이너 처리 상태 polling — FINISHED 또는 ERROR 까지 대기."""
    url = f"https://graph.facebook.com/v21.0/{container_id}?fields=status_code,status&access_token={token}"
    waited = 0
    while waited < max_seconds:
        req = urllib.request.Request(url)
        try:
            with urllib.request.urlopen(req) as r:
                body = json.loads(r.read())
        except urllib.error.HTTPError as e:
            body = json.loads(e.read())
        status = body.get("status_code") or body.get("status", "?")
        if status in ("FINISHED", "PUBLISHED"):
            return True, status
        if status == "ERROR":
            return False, body
        time.sleep(interval)
        waited += interval
    return False, f"timeout after {max_seconds}s"


def create_carousel_container(ig_id, token, children_ids, caption):
    """캐러셀 컨테이너 생성"""
    data = {
        "media_type": "CAROUSEL",
        "children": ",".join(children_ids),
        "caption": caption,
        "access_token": token,
    }
    result = api_post(f"https://graph.facebook.com/v21.0/{ig_id}/media", data)
    return result.get("id")


def publish_container(ig_id, token, container_id):
    """컨테이너 발행"""
    data = {
        "creation_id": container_id,
        "access_token": token,
    }
    result = api_post(f"https://graph.facebook.com/v21.0/{ig_id}/media_publish", data)
    return result.get("id")


def post_single_image(ig_id, token, image_url, caption):
    """단일 이미지 포스팅"""
    data = {
        "image_url": image_url,
        "caption": caption,
        "access_token": token,
    }
    result = api_post(f"https://graph.facebook.com/v21.0/{ig_id}/media", data)
    container_id = result.get("id")
    if not container_id:
        return None, result

    time.sleep(2)
    post_id = publish_container(ig_id, token, container_id)
    return post_id, None


def post_carousel(ig_id, token, urls, caption, media_type="image"):
    """캐러셀(다중 슬라이드) 포스팅. media_type='image'|'video'."""
    is_video = media_type == "video"
    label = "비디오" if is_video else "이미지"
    print(f"  {len(urls)}장 {label} 컨테이너 생성 중...")
    children = []
    for i, url in enumerate(urls):
        if is_video:
            cid = create_video_container(ig_id, token, url)
        else:
            cid = create_image_container(ig_id, token, url)
        if not cid:
            print(f"  ✗ 슬라이드 {i+1} 컨테이너 생성 실패: {url}")
            return None, "container_creation_failed"
        children.append(cid)
        print(f"  ✓ 슬라이드 {i+1}/{len(urls)} 컨테이너 생성 (id={cid})")
        time.sleep(1)

    # 비디오는 processing 단계가 길다 — 각 child가 FINISHED 될 때까지 polling
    if is_video:
        print(f"  비디오 처리 대기 (최대 120s/슬라이드)...")
        for i, cid in enumerate(children):
            ok, info = poll_container_status(token, cid, max_seconds=120)
            if not ok:
                print(f"  ✗ 슬라이드 {i+1} 처리 실패: {info}")
                return None, f"video_processing_failed: {info}"
            print(f"  ✓ 슬라이드 {i+1} 처리 완료")

    print("  캐러셀 컨테이너 생성 중...")
    carousel_id = create_carousel_container(ig_id, token, children, caption)
    if not carousel_id:
        return None, "carousel_creation_failed"
    print(f"  ✓ 캐러셀 컨테이너 생성 (id={carousel_id})")

    # 캐러셀 컨테이너도 FINISHED 까지 polling (비디오 캐러셀은 추가 처리 필요)
    if is_video:
        print(f"  캐러셀 처리 대기 (최대 180s)...")
        ok, info = poll_container_status(token, carousel_id, max_seconds=180)
        if not ok:
            print(f"  ✗ 캐러셀 처리 실패: {info}")
            return None, f"carousel_processing_failed: {info}"
        print(f"  ✓ 캐러셀 처리 완료")
    else:
        time.sleep(3)

    print("  발행 중...")
    publish_result = publish_container_with_result(ig_id, token, carousel_id)
    post_id = publish_result.get("id") if isinstance(publish_result, dict) else None
    if not post_id:
        return None, f"publish_failed: {publish_result}"
    verified = publish_result.get("_verified_via_media")
    return post_id, ("rate_limit_but_published" if verified else None)


def publish_container_with_result(ig_id, token, container_id):
    """Publish + return full result for better error reporting.
    Meta API sometimes returns a rate-limit error AFTER actually publishing.
    On error, we verify by checking the account's most recent media.
    """
    import time as _time
    data = {
        "creation_id": container_id,
        "access_token": token,
    }
    result = api_post(f"https://graph.facebook.com/v21.0/{ig_id}/media_publish", data)
    if result.get("id"):
        return result
    # Got an error response — verify whether the post actually published
    _time.sleep(5)
    try:
        import urllib.request as _ur
        check_url = f"https://graph.facebook.com/v21.0/{ig_id}/media?fields=id,timestamp&limit=3&access_token={token}"
        with _ur.urlopen(_ur.Request(check_url)) as r:
            recent = json.loads(r.read())
        items = recent.get("data", [])
        if items:
            # If newest post is within last 60 seconds, assume our publish succeeded
            from datetime import datetime, timezone
            newest_ts = datetime.fromisoformat(items[0]["timestamp"].replace("Z", "+00:00"))
            age = (datetime.now(timezone.utc) - newest_ts).total_seconds()
            if age < 60:
                print(f"  ⚠️  API returned error but post appears published (age {age:.0f}s) — treating as success")
                return {"id": items[0]["id"], "_verified_via_media": True}
    except Exception as e:
        pass
    return result


def build_caption(title, summary, url, tags):
    """인스타그램 캡션 구성"""
    hashtags = ""
    if tags:
        tag_list = [t.strip().lstrip("#") for t in tags.split(",") if t.strip()]
        hashtags = "\n\n" + " ".join(f"#{t}" for t in tag_list)

    caption = f"{title}"
    if summary:
        caption += f"\n\n{summary}"
    if url:
        caption += f"\n\n🔗 {url}"
    caption += f"\n\n👉 링크는 프로필 바이오에서도 확인"
    caption += hashtags
    return caption


def main():
    parser = argparse.ArgumentParser(description="Instagram 카드뉴스 포스팅 (기본: 캐러셀, 2~10장)")
    parser.add_argument("--title", required=True, help="블로그 글 제목")
    parser.add_argument("--url", required=True, help="블로그 글 URL")
    parser.add_argument("--summary", default="", help="1~2줄 요약")
    parser.add_argument("--images", default="",
                        help="이미지 URL 목록 (쉼표 구분). 정지 PNG 캐러셀.")
    parser.add_argument("--videos", default="",
                        help="비디오 URL 목록 (쉼표 구분). B 단계 MP4 카드뉴스 캐러셀.")
    parser.add_argument("--tags", default="", help="해시태그 (쉼표 구분)")
    parser.add_argument("--single", action="store_true",
                        help="단일 슬라이드 포스팅 허용 (기본은 캐러셀 강제)")
    parser.add_argument("--dry-run", action="store_true", help="실제 발행 안 함")
    args = parser.parse_args()

    image_urls = [u.strip() for u in args.images.split(",") if u.strip()]
    video_urls = [u.strip() for u in args.videos.split(",") if u.strip()]

    if image_urls and video_urls:
        print("ERROR: --images와 --videos는 동시 사용 불가. 하나만 선택하세요.")
        sys.exit(1)

    media_urls = video_urls if video_urls else image_urls
    media_type = "video" if video_urls else "image"

    if not media_urls:
        print("ERROR: --images 또는 --videos URL 목록이 필요합니다.")
        sys.exit(1)
    if len(media_urls) == 1 and not args.single:
        print(f"ERROR: 캐러셀이 default입니다. {media_type} 2~10장 공급 또는 --single 플래그 사용.")
        sys.exit(2)
    if len(media_urls) > 10:
        print("WARNING: Instagram 캐러셀 최대 10장. 처음 10장만 사용합니다.")
        media_urls = media_urls[:10]

    caption = build_caption(args.title, args.summary, args.url, args.tags)

    print("=" * 50)
    print(f"Instagram 카드뉴스 미리보기 ({media_type})")
    print("=" * 50)
    print("계정: configured Instagram Business account")
    print(f"슬라이드 수: {len(media_urls)}장")
    print(f"\n[캡션]\n{caption}")
    print(f"\n[{media_type} 목록]")
    for i, url in enumerate(media_urls):
        print(f"  슬라이드 {i+1}: {url[:80]}...")
    print("=" * 50)

    if args.dry_run:
        print("✓ [DRY RUN] 실제 발행 안 함")
        return

    env = load_env()
    token = env.get("META_GRAPH_TOKEN", "")
    ig_id = env.get("INSTAGRAM_BUSINESS_ACCOUNT_ID", "")

    if not token:
        print("ERROR: META_GRAPH_TOKEN이 .env에 없습니다.")
        sys.exit(1)
    if not ig_id:
        print("ERROR: INSTAGRAM_BUSINESS_ACCOUNT_ID가 .env에 없습니다.")
        sys.exit(1)

    if len(media_urls) == 1 and media_type == "image":
        print("단일 이미지 포스팅 중...")
        post_id, err = post_single_image(ig_id, token, media_urls[0], caption)
    else:
        print(f"{media_type} 캐러셀 포스팅 중...")
        post_id, err = post_carousel(ig_id, token, media_urls, caption, media_type=media_type)

    if post_id:
        if err == "rate_limit_but_published":
            print(f"\n✓ 발행 성공! (API rate-limit 에러 수신했으나 실제 발행 확인됨)")
        else:
            print(f"\n✓ 발행 성공!")
        print(f"  Post ID: {post_id}")
        print(f"  URL: https://www.instagram.com/p/{post_id}/")
        log_publish(
            'instagram',
            post_id,
            url=f'https://www.instagram.com/p/{post_id}/',
            title=args.title,
            blog_url=args.url,
            image_url=media_urls[0] if media_urls else '',
            extra={'slide_count': len(media_urls), 'media_type': media_type},
        )
    else:
        print(f"\n✗ 발행 실패: {err}")
        sys.exit(1)


if __name__ == "__main__":
    main()
