# 기술 블로그 자동화

이 저장소는 기술 블로그와 블로그 기반 SNS 배포 자동화 흐름을 관리합니다.
이번 업데이트는 **이미지 생성**, **SNS 병렬 발행**, **영문 소스의 한국어 윤문 품질검증**을 더 안전하고 일관되게 만드는 데 초점을 맞췄습니다.

## 이번 PR의 핵심

### 1. 이미지 생성 기본값 정리

이미지 생성 기본 모델은 OpenAI `gpt-image-2`입니다.
Local Bonsai와 Minimax는 기본값이 아니라 fallback 또는 실험 프로필에서 사용합니다.

기본 순서:

1. OpenAI `gpt-image-2`
2. Local Bonsai Image 4B
3. Minimax
4. `IMAGE_GENERATION_FAILED`

### 2. 병렬 이미지 생성 프로필

`scripts/sns/parallel_image_request.py`는 블로그+SNS 이미지 요청을 3장씩 나누어 병렬 생성 요청서로 만듭니다.

지원 프로필:

- `default`: 모든 이미지 `gpt-image-2` 우선
- `hybrid`: Threads 4컷만 Local Bonsai 우선, 나머지는 `gpt-image-2`
- `experimental`: 채널별 모델 분리 실험용

Instagram 카드뉴스는 5장을 `instagram-carousel` 그룹으로 묶습니다. 일부 슬라이드만 다른 모델로 섞어 발행하지 않는 것이 기본 원칙입니다.

### 3. SNS 발행 경로 복구

`scripts/sns/parallel_sns_publish.py`는 다음 순서로 SNS를 발행합니다.

1. Threads 먼저 발행
2. Instagram과 Facebook 동시 발행
3. 결과를 통합 보고

Instagram은 기본적으로 캐러셀 2~10장을 요구하며, 1장 발행은 `--single`이 있을 때만 허용합니다.

### 4. 한국어 번역 윤문 품질 게이트

영문 소스를 한국어 블로그로 바꿀 때 AI 번역투가 남지 않도록 `scripts/quality/translation_naturalness_gate.py`를 추가했습니다.

검사 항목:

- 중국어/일본어 등 CJK 문자 잔존
- `시사합니다`, `전망입니다`, `할 것입니다`, `가능성이 있습니다` 같은 반복적 번역투
- `production-ready`, `Robust`, `Inclusive`처럼 미번역으로 남기 쉬운 영어 표현 과다

이 게이트가 실패하면 발행 전에 `humanize-korean` 윤문 단계를 다시 거치는 것을 원칙으로 합니다.

## 보안 원칙

이 저장소에는 절대 커밋하지 않습니다.

- API 키
- Meta Graph token
- OpenAI 키 또는 OAuth 토큰
- `.env` 파일
- 개인 메모리 파일
- 로컬 작업공간 내부 상태
- 임시 출력물과 런 로그

실행에 필요한 값은 로컬 환경 또는 CI secret으로만 제공합니다.

필수 환경변수 예:

```bash
META_GRAPH_TOKEN=...
INSTAGRAM_BUSINESS_ACCOUNT_ID=...
INSTAGRAM_PAGE_ID=...
OPENCLAW_ENV_FILE=~/.openclaw/.env
BONSAI_DEMO_DIR=~/.openclaw/Bonsai-Image-Demo
```

## 빠른 사용 예시

이미지 요청서 생성:

```bash
python3 scripts/sns/parallel_image_request.py --profile default
```

번역 자연스러움 검사:

```bash
python3 scripts/quality/translation_naturalness_gate.py content/posts/example.md
```

SNS 발행 드라이런:

```bash
python3 scripts/sns/parallel_sns_publish.py \
  --blog-url "https://example.com/posts/demo/" \
  --title "Demo Post" \
  --threads-image "https://example.com/threads.png" \
  --threads-posts "1/3 요약" "2/3 핵심" "3/3 링크" \
  --ig-images "https://example.com/1.png,https://example.com/2.png" \
  --ig-caption "Instagram caption" \
  --fb-image "https://example.com/cover.png" \
  --fb-summary "Facebook summary" \
  --dry-run
```
