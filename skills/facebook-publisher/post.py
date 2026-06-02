#!/usr/bin/env python3
"""Facebook page posting script."""

import os
import sys
import json
import argparse
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


def api_get(url):
    with urllib.request.urlopen(url) as r:
        return json.loads(r.read())


def api_post(url, data: dict):
    payload = urllib.parse.urlencode(data).encode()
    req = urllib.request.Request(url, data=payload, method="POST")
    try:
        with urllib.request.urlopen(req) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return json.loads(e.read())


def post_link(page_id, token, message, link, image_url=None):
    """링크 포스트 (블로그 글 공유)"""
    base = f"https://graph.facebook.com/v21.0/{page_id}/feed"
    data = {
        "message": message,
        "link": link,
        "access_token": token,
    }
    return api_post(base, data)


def post_photo(page_id, token, message, image_url):
    """이미지 + 텍스트 포스트"""
    base = f"https://graph.facebook.com/v21.0/{page_id}/photos"
    data = {
        "message": message,
        "url": image_url,
        "access_token": token,
    }
    return api_post(base, data)


def post_video(page_id, token, message, video_url):
    """동영상 포스트 (file_url 방식)"""
    base = f"https://graph.facebook.com/v21.0/{page_id}/videos"
    data = {
        "description": message,
        "file_url": video_url,
        "access_token": token,
    }
    return api_post(base, data)


def main():
    parser = argparse.ArgumentParser(description="Facebook 페이지 포스팅")
    parser.add_argument("--title", required=True, help="블로그 글 제목")
    parser.add_argument("--url", required=True, help="블로그 글 URL")
    parser.add_argument("--summary", default="", help="1~2줄 요약")
    parser.add_argument("--image", default="", help="이미지 URL (선택)")
    parser.add_argument("--video", default="", help="동영상 URL (선택, --image보다 우선)")
    parser.add_argument("--tags", default="", help="해시태그 (쉼표 구분)")
    parser.add_argument("--dry-run", action="store_true", help="실제 발행 안 함")
    args = parser.parse_args()

    # 해시태그 처리
    hashtags = ""
    if args.tags:
        tags = [t.strip().lstrip("#") for t in args.tags.split(",") if t.strip()]
        hashtags = "\n\n" + " ".join(f"#{t}" for t in tags)

    # 메시지 구성
    message = f"{args.title}"
    if args.summary:
        message += f"\n\n{args.summary}"
    message += f"\n\n▶ {args.url}"
    message += hashtags

    print("=" * 50)
    print("Facebook 포스팅 미리보기")
    print("=" * 50)
    print("페이지: configured Facebook Page")
    print(f"메시지:\n{message}")
    if args.image:
        print(f"이미지: {args.image}")
    print("=" * 50)

    if args.dry_run:
        print("✓ [DRY RUN] 실제 발행 안 함")
        return

    env = load_env()
    token = env.get("META_GRAPH_TOKEN", "")
    page_id = env.get("INSTAGRAM_PAGE_ID", "")

    if not token:
        print("ERROR: META_GRAPH_TOKEN이 .env에 없습니다.")
        sys.exit(1)
    if not page_id:
        print("ERROR: INSTAGRAM_PAGE_ID가 .env에 없습니다.")
        sys.exit(1)

    # 발행 (video > image > link 우선순위)
    if args.video:
        result = post_video(page_id, token, message, args.video)
        mode = 'video'
        media_url = args.video
    elif args.image:
        result = post_photo(page_id, token, message, args.image)
        mode = 'photo'
        media_url = args.image
    else:
        result = post_link(page_id, token, message, args.url)
        mode = 'link'
        media_url = ''

    if "id" in result:
        post_id = result["id"]
        post_url = f"https://www.facebook.com/{post_id.replace('_', '/posts/')}"
        print(f"✓ 발행 성공! ({mode})")
        print(f"  Post ID: {post_id}")
        print(f"  URL: {post_url}")
        log_publish(
            'facebook',
            post_id,
            url=post_url,
            title=args.title,
            blog_url=args.url,
            image_url=media_url,
            extra={'mode': mode},
        )
    else:
        print(f"✗ 발행 실패: {json.dumps(result, ensure_ascii=False)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
