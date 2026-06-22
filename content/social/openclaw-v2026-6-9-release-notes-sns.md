# OpenClaw v2026.6.9 릴리즈 노트 SNS 콘텐츠

- source_url: https://github.com/openclaw/openclaw/releases/tag/v2026.6.9
- blog_url: https://noahrha.github.io/posts/openclaw-v2026-6-9-release-notes/
- status: draft
- selected_threads: 3분할 — 본문 + 댓글 2개
- selected_instagram_cardnews: 5장 구성
- selected_at: 2026-06-22 15:08 Asia/Seoul

---

## Threads 최종본 (3분할)

### p1 — 본문

OpenClaw v2026.6.9가 올라왔습니다. 이번에는 보이지 않는 곳을 단단히 조이는 쪽입니다.

가장 무거운 변경은 텔레그램과 에이전트 복원력입니다. 텔레그램이 진짜 리치 HTML로 메시지를 보내고, 마크다운 줄바꿈·스티커 경로·표 정규화까지 함께 들어갔습니다.

에이전트는 사고만 하다 끝난 턴, 후속이 빈 턴, 컴팩션 뒤 사라지던 사용량을 모두 살려냅니다. "성공했는데 답이 안 보이는" 케이스가 줄어드는 흐름입니다.

머지된 PR은 422개, 큰 릴리즈입니다.

### p2 — 댓글 1

Codex 통합이 더 깊어졌습니다. 플러그인 자동 승인이 들어왔고, GPT-5.3 Spark OAuth 라우팅이 복원됐습니다. 원격 노드 `exec`는 이제 동적 도구로 풀려서 Codex 안에서 바로 부를 수 있습니다.

외부 프로바이더 플러그인은 npm 정식 패키지로 독립 발행됩니다. 본체와 라이프사이클을 분리할 수 있게 됐고, StepFun이 첫 사례로 npm과 ClawHub 양쪽에서 잡힙니다.

ClawHub 스킬 설치는 검증된 출처를 그대로 보관합니다.

### p3 — 댓글 2

클라이언트 쪽도 풍부해졌습니다.

컨트롤 UI에는 세션 워크스페이스 레일과 확장 헬스 표시가 새로 들어왔고, iOS는 Watch 컨트롤, Android는 채팅 컨텍스트 사용량을 보여 줍니다.

보안은 시크릿 마스킹, 내부 HTTP 세션 오버라이드 차단, 오픈 DM 도구 노출 감사를 유지합니다. 저장소 쪽은 네트워크 파일시스템에서 SQLite WAL을 피하고, 재인덱스 사이드카를 안전하게 교체합니다.

전체 정리는 블로그에서 확인하실 수 있습니다.

▶ https://noahrha.github.io/posts/openclaw-v2026-6-9-release-notes/

---

## Instagram 카드뉴스 5장

### 1장 — 후킹

**OpenClaw v2026.6.9
기본기를 다지는 큰 업데이트**

422개 PR이 머지된 6.9, 어디부터 봐야 할까요.

### 2장 — 텔레그램 리치 전달

리치 HTML로 메시지를 직접 송신.
마크다운 줄바꿈 유지, 스티커 경로 보존,
HTML 표 안전 정규화.

진행 중 임시 메시지도
풍부한 프리뷰로 렌더됩니다.

### 3장 — 에이전트 복원력

사고만 하다 끝난 턴 자동 재시도.
컴팩션 이후 사용량 보존.
세션 히스토리·답장 큐 복구까지.

"성공했는데 답이 안 보이는"
케이스를 줄여 줍니다.

### 4장 — Codex와 플러그인

플러그인 자동 승인, GPT-5.3 Spark OAuth 복원.
원격 노드 `exec`가 동적 도구로 노출.

공식 프로바이더가 npm 정식 패키지로
독립 발행됩니다.

### 5장 — CTA

컨트롤 UI 세션 워크스페이스 레일,
iOS Watch, Android 채팅 컨텍스트까지.

OpenClaw v2026.6.9의 전체 변경점,
NoahRha 블로그에 정리했습니다.

▶ https://noahrha.github.io/posts/openclaw-v2026-6-9-release-notes/

---

## Instagram 캡션 최종 후보

OpenClaw v2026.6.9는 보이지 않는 곳을 단단히 조이는 릴리즈입니다.

텔레그램이 진짜 리치 HTML로 메시지를 보내고, 마크다운·스티커·표가 모바일에서도 깨지지 않습니다. 에이전트는 사고만 하다 끝난 턴, 컴팩션 뒤 사라지던 사용량까지 복구합니다. Codex는 플러그인 자동 승인과 원격 노드 `exec` 호출을 풀어 한 발 더 들어갔고, 외부 프로바이더는 npm에서 독립 패키지로 발행됩니다.

자세한 정리는 NoahRha 블로그에 올렸습니다.

#OpenClaw #릴리즈노트 #AI에이전트 #Telegram #Codex #플러그인 #자동화 #NoahRha
