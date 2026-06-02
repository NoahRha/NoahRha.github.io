---
name: facebook-publisher
description: >
  블로그 글을 환경변수로 설정된 Facebook 페이지에 자동 포스팅하는 스킬.
  링크 공유 또는 이미지+텍스트 포맷으로 발행.
  Use when: "페이스북에 올려줘", "FB 포스팅", "Facebook 페이지에 게시" 요청 시.
  환경변수: META_GRAPH_TOKEN (Page Token), INSTAGRAM_PAGE_ID
---

# Facebook Publisher

블로그 글 → Facebook 페이지 자동 포스팅

## 포스팅 포맷

```
[제목]

[1~2줄 요약]

▶ [블로그 URL]

#태그1 #태그2 #태그3
```

## 사용법

**스크립트는 저장소 기준 경로를 사용한다.** Python 실행 파일은 환경에 맞게 `PYTHON_BIN` 또는 `python3`로 지정한다.

```bash
# 링크 포스팅 (기본)
python3 skills/facebook-publisher/post.py \
  --title "번개는 어떻게 생길까?" \
  --url "https://techllm.github.io/posts/what-causes-lightning-science/" \
  --summary "번개의 비밀, 과학자들도 아직 다 모른다." \
  --tags "과학,번개,물리학"

# 커버 이미지 포함
python3 skills/facebook-publisher/post.py \
  --title "제목" \
  --url "https://..." \
  --image "https://커버이미지URL" \
  --summary "요약"

# 테스트 (실제 발행 안 함)
python3 skills/facebook-publisher/post.py \
  --title "제목" --url "https://..." --dry-run
```

## 환경변수 (.env)

| 변수 | 설명 |
|------|------|
| `META_GRAPH_TOKEN` | Meta Graph API Page Access Token (영구). Facebook 페이지·Instagram Business 계정 공용. |
| `INSTAGRAM_PAGE_ID` | Facebook Page ID. 저장소에 실제 값을 커밋하지 않는다. |

> `INSTAGRAM_ACCESS_TOKEN`은 legacy instagram-api 스킬용으로만 유지. 새 워크플로는 `META_GRAPH_TOKEN`을 사용한다.

## 워크플로우 (블로그 발행 후 자동 연계)

1. Hugo 블로그 글 발행
2. Threads 포스팅 (threads-toolkit 스킬)
3. **Facebook 포스팅 (이 스킬)** ← 블로그 URL + 커버 이미지 사용
4. Instagram 카드뉴스 (instagram-cardnews 스킬)
