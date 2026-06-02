---
name: instagram-cardnews
description: >
  블로그 글을 Instagram 카드뉴스(캐러셀) 또는 단일 이미지 포스팅으로 자동 발행.
  환경변수로 설정된 Instagram Business 계정 사용. 최대 10장 슬라이드 지원.
  Use when: "인스타 카드뉴스 올려줘", "인스타그램 포스팅", "IG 캐러셀" 요청 시.
---

# Instagram 카드뉴스 스킬

블로그 글 → Instagram 카드뉴스(캐러셀) 자동 포스팅

## 기본 정책: 캐러셀 (2~10장)

**default는 캐러셀 발행이다.** 인스타그램 알고리즘이 캐러셀에 더 많은 도달을 부여하고, 카드뉴스는 본 스킬의 핵심 가치다. 단일 이미지는 명시적 `--single` 플래그가 있을 때만 허용.

- `--images` 1장 + `--single` 없음 → 에러 (exit 2), 캐러셀 권유
- `--images` 1장 + `--single` 명시 → 단일 이미지 발행 (Threads/Facebook 첨부 이미지와 가치 차이가 작으므로 의도적 선택일 때만)
- `--images` 2~10장 → 캐러셀 발행 (default)

### 캐러셀 슬라이드 자동 생성 워크플로 (호출자가 책임)
`post.py`/`generate_cards.py`는 공개 이미지 URL을 받는다. 슬라이드 이미지 자체는 상위 워크플로(스킬 호출자)가 준비:
1. 블로그 본문 섹션별로 키 메시지 추출 (3~7개)
2. 슬라이드별 카드 이미지를 **1:1 (권장 1080×1080 또는 1024×1024)** 로 생성 — 작업 시작 시 정한 스타일(핸드드로잉 또는 유화)을 5장 모두 동일 적용
   - 기본 생성: Codex `imagegen` 스킬 built-in `image_gen` (`gpt-image-2`, OAuth 기반)
   - fallback: `scripts/generate_bonsai.sh` → Minimax
   - 병렬 생성 시 `ig-slide-*` 5장은 `instagram-carousel` 재생성 그룹으로 묶는다. 일부 슬라이드만 다른 모델로 섞어 발행하지 않는다.
   - 핸드드로잉 필수 구절: `"masterful hand-drawn ink illustration, expert pen and ink artwork, bold confident strokes, detailed cross-hatching shading, editorial illustration quality"`
   - 유화 필수 구절: `"rich oil painting style, masterful brushstrokes, painterly texture, fine art quality, museum-worthy artwork"`
   - 일러스트 없이 텍스트만 있는 카드는 생성 거부 기준 위반
3. 각 이미지를 catbox/CDN에 업로드 → public URL 확보
4. URL을 쉼표로 묶어 `--images "url1,url2,url3,..."` 호출

## 카드뉴스 구성 원칙

| 슬라이드 | 내용 |
|---------|------|
| 1장 (커버) | 제목 + 핵심 질문 (시선을 끄는 이미지) |
| 2~5장 (본문) | 핵심 포인트 1개씩, 한 문장으로 |
| 마지막 장 | 결론 + CTA ("링크는 프로필 바이오에서") |

## 캡션 포맷

```
[제목]

[1~2줄 요약]

🔗 링크는 프로필 바이오에서

#태그1 #태그2 #태그3
```

## 사용법

**스크립트는 저장소 기준 경로를 사용한다.** Python 실행 파일은 환경에 맞게 `PYTHON_BIN` 또는 `python3`로 지정한다.

```bash
# 통합 SNS 파이프라인용 wrapper (caption 완성본을 그대로 게시)
python3 skills/instagram-cardnews/post.py \
  --title "제목" \
  --url "https://..." \
  --images "https://슬라이드1.jpg,https://슬라이드2.jpg,https://슬라이드3.jpg,https://슬라이드4.jpg,https://슬라이드5.jpg" \
  --caption "완성된 인스타그램 캡션" \
  --tags "태그1,태그2"

# 캐러셀 (default, 2~10장)
python3 skills/instagram-cardnews/generate_cards.py \
  --title "제목" \
  --url "https://..." \
  --images "https://슬라이드1.jpg,https://슬라이드2.jpg,https://슬라이드3.jpg" \
  --tags "태그1,태그2"

# 단일 이미지 (의도적 선택일 때만 --single)
python3 skills/instagram-cardnews/generate_cards.py \
  --title "번개는 어떻게 생길까?" \
  --url "https://..." \
  --summary "과학자들도 아직 다 모르는 번개의 비밀" \
  --images "https://커버이미지URL" \
  --single \
  --tags "과학,번개,물리학"

# 테스트 (캐러셀)
python3 skills/instagram-cardnews/generate_cards.py \
  --title "제목" --url "https://..." --images "https://s1.jpg,https://s2.jpg" --dry-run
```

## 이미지 준비 방법

### 방법 A — 블로그 본문 이미지 재활용
블로그 글 내 이미지 URL을 슬라이드로 사용

### 방법 B — 커버 이미지만 사용 (단일 포스팅)
블로그 커버 이미지 1장으로 링크 소개형 포스팅

### 방법 C — AI 이미지 생성
OpenAI `gpt-image-2` built-in `image_gen`을 기본으로 사용한다. 모든 슬라이드는 1:1이며 한 작업 안에서 스타일을 섞지 않는다. Local Bonsai는 fallback 또는 형님이 지정한 특수 용도다.

병렬 이미지 dispatcher를 사용할 때는 기본 `--profile default`를 사용한다. `experimental` 프로필처럼 채널별 모델을 나눠 쓰는 경우에도 Instagram 캐러셀은 5장 단위로 같은 모델/스타일을 유지해야 한다.

## 환경변수 (.env)

| 변수 | 설명 |
|------|------|
| `META_GRAPH_TOKEN` | Meta Graph API Page Access Token (영구). Facebook 페이지·Instagram Business 계정 공용. |
| `INSTAGRAM_BUSINESS_ACCOUNT_ID` | Instagram Business Account ID. 저장소에 실제 값을 커밋하지 않는다. |

> `INSTAGRAM_ACCESS_TOKEN`은 legacy instagram-api 스킬용으로만 유지. 새 워크플로는 `META_GRAPH_TOKEN`을 사용한다.

## 전체 워크플로우

```
블로그 발행
  → Threads (threads-toolkit)
  → Facebook (facebook-publisher)
  → Instagram 카드뉴스 (이 스킬)
```
