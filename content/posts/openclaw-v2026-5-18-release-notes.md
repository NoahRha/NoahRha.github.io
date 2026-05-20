---
title: "OpenClaw 2026.5.18: 플러그인 SDK, 스킬 대거 추가, Mac 설정 UI 개편"
date: 2026-05-20T14:58:00+09:00
draft: false
description: "OpenClaw 2026.5.18이 출시됐다. 타입드 플러그인 SDK, meme-maker·Python 디버깅·노드 인스펙터 등 스킬 신규 추가, Mac 앱 설정 페이지 전면 리디자인, Gateway 재시작 지연 개선, QA-Lab 런타임 패리티 체계 강화가 핵심이다."
cover:
  image: "/images/openclaw-v2026-5-18-cover.png"
  alt: "OpenClaw 2026.5.18 릴리스"
  caption: ""
tags:
  - OpenClaw
  - 릴리스노트
  - AI에이전트
  - 플러그인
  - 스킬
categories:
  - OpenClaw
---

OpenClaw 2026.5.18이 출시됐다. 이번 릴리스는 타입드 플러그인 SDK 도입, 스킬 대거 신규 추가, Mac 앱 설정 UI 전면 개편, Gateway 재시작 지연 단축, QA-Lab 런타임 패리티 체계 강화가 핵심이다. 커뮤니티 기여자 다수가 참여했다.

## 핵심 요약

- **플러그인 SDK**: `defineToolPlugin` + `openclaw plugins build/validate/init` 명령으로 타입드 심플 툴 플러그인 개발 환경 완성
- **스킬 신규**: meme-maker, Python 디버거, 노드 인스펙터, 다이어그램 생성, 스파이크 워크플로우 5종 추가
- **Mac 앱**: Settings 페이지 전면 카드 레이아웃으로 리디자인, 네비게이션 캐싱
- **Gateway**: 채널 사이드카와 플러그인 서비스 시작을 병렬화해 재시작 지연 단축
- **QA-Lab**: 20-turn/100-turn 런타임 패리티 시나리오, `--runtime-parity-tier` 옵션 추가
- **Docker**: `OPENCLAW_IMAGE_APT_PACKAGES` 런타임 중립 빌드 인수 추가

## 플러그인 SDK — 타입드 심플 툴 플러그인

이번 릴리스의 가장 큰 변화 중 하나다. `defineToolPlugin`을 통해 타입드 심플 툴 플러그인을 선언할 수 있게 됐고, 새 CLI 명령 3종이 추가됐다.

```bash
openclaw plugins build    # 플러그인 빌드
openclaw plugins validate # 매니페스트 검증
openclaw plugins init     # 새 플러그인 초기화
```

생성된 매니페스트 메타데이터, 선택적 툴 선언, 컨텍스트 팩토리를 지원한다. 플러그인 개발자라면 이제 명확한 타입 기반 워크플로우로 작업할 수 있다.

**Admin HTTP RPC** 측면에서는 신뢰된 관리자 클라이언트가 웹 QR 로그인 플로우를 시작하고 대기할 수 있게 됐다. ([PR #83259](https://github.com/openclaw/openclaw/pull/83259), @liorb-mountapps)

**플러그인 메시지** 쪽에서는 채널 렌더러의 프레젠테이션 capability limit이 추가됐고, 네이티브 렌더링 전 리치 메시지 컨트롤이 적용된다. 레거시 인터랙티브/Slack 디렉티브 프로듀서 API는 deprecated 처리됐다.

## 스킬 5종 신규 추가

### meme-maker
큐레이션된 밈 템플릿 검색, 로컬 SVG/PNG 렌더링, Imgflip 호스팅 렌더링, Know Your Meme 출처 링크까지 지원한다. 소셜 콘텐츠 작업에 바로 활용 가능하다.

### Python 디버거
`pdb`, `breakpoint()`, 사후 인스펙션(post-mortem), `debugpy` 원격 어태치까지 지원하는 Python 디버깅 스킬이 추가됐다. 에이전트 기반 Python 개발 워크플로우가 크게 강화된다.

### 노드 인스펙터 디버깅
Node.js 인스펙터 프로토콜 기반 디버깅 스킬이 추가됐다.

### 다이어그램 생성 (Fused)
퓨즈드 다이어그램 생성 스킬로 복잡한 시스템 구조를 빠르게 시각화할 수 있다.

### 스파이크 워크플로우
일회성 아이디어 검증을 위한 throwaway spike 워크플로우 스킬이 추가됐다.

**기타 스킬 변경사항:**
- Codex closeout 리뷰 스킬 이름이 `autoreview`로 변경됐다 (Codex-first 폴백 동작은 유지)
- Obsidian 스킬이 서드파티 `obsidian-cli` 대신 공식 obsidian CLI를 대상으로 업데이트됐다
- 번들 스킬 프롬프트와 메타데이터가 정비됐고, sherpa-onnx 런타임 다운로드도 업데이트됐다

## Mac 앱 — Settings 전면 리디자인

Mac 앱의 Settings 페이지가 전면 개편됐다.

- **카드 레이아웃**: 모든 설정 페이지에 일관된 카드 레이아웃 적용
- **네비게이션 캐싱**: 페이지 간 이동 시 상태 유지
- **클리너 패널**: Permissions, Voice, Skills, Cron, Exec, Debug 패널 정리
- **네이티브 사이드바 여백 개선**: 일관된 간격

## Gateway 재시작 지연 단축

두 건의 개선이 합쳐져 Gateway 재시작 시 준비 완료까지 걸리는 시간이 줄었다.

- **시작 로그와 채널 사이드카 병렬화** ([PR #83301](https://github.com/openclaw/openclaw/pull/83301), @samzong): 플러그인 서비스 시작과 채널 사이드카를 겹쳐 실행해 재시작 대기 지연을 줄인다. `/readyz` 사이드카 게이팅은 그대로 유지.
- **ACPX 시작 프로브 비용 추적** ([PR #83300](https://github.com/openclaw/openclaw/pull/83300), @samzong): 시작 프로브, 설정, 런타임, 리소스 카운트 비용을 재시작 트레이스에 포함시켰다. Readiness 동작에는 영향 없음.

## 브라우저 — 모달 다이얼로그 지원

- 스냅샷에 보류 중이거나 최근 처리된 모달 다이얼로그가 노출된다
- 액션이 모달을 열면 `blockedByDialog`를 반환한다
- `--dialog-id`로 보류 중인 다이얼로그에 응답할 수 있다

브라우저 자동화 중 모달 처리 시나리오가 훨씬 명확해진다.

## QA-Lab — 런타임 패리티 체계 강화

QA-Lab에 여러 건의 개선이 한꺼번에 들어왔다.

- **20-turn / 100-turn 시나리오**: 1시간 내 첫 실행 및 선택적 100-turn 런타임 패리티 시나리오 추가. standard/soak QA 게이트에 tier 메타데이터 포함.
- **`--runtime-parity-tier` 옵션**: `openclaw qa suite`에 추가. standard Codex-vs-Pi tier를 옵션/live-only/soak 레인과 분리해 릴리스 체크에 연결.
- **Read 어휘 카나리**: live-only Codex Pi-shaped Read 어휘 카나리를 추가해 네이티브 워크스페이스 read 프롬프트 호환성 드리프트를 감지.
- **하네스 자가 상태 점검**: 플러그인 훅 크래시, 매니페스트 계약 오류, WebChat 다이렉트 리플라이 자가 메시지 라우팅 시나리오 추가.
- **런타임 툴 픽스처 시나리오**: Codex-native 워크스페이스 툴, OpenClaw 다이나믹 툴, 옵션 플러그인 백드 툴에 대한 커버리지 리포팅 추가.

## Docker/Proxy/기타

- **Docker**: `OPENCLAW_IMAGE_APT_PACKAGES`가 런타임 중립 이미지 빌드 인수로 추가됐다. 기존 `OPENCLAW_DOCKER_APT_PACKAGES`는 레거시 폴백으로 유지. ([PR #62431](https://github.com/openclaw/openclaw/pull/62431), @urtabajev)
- **Proxy**: HTTPS 매니지드 포워드 프록시 엔드포인트 지원 추가, `proxy.tls.caFile` CA 신뢰 스코핑 지원. ([PR #79171](https://github.com/openclaw/openclaw/pull/79171), @jesse-merhi)
- **에이전트 툴**: 미디어, 메시징, 세션, Cron, Gateway, 웹, 이미지/PDF, TTS, 노드, 플랜 툴 전반의 내장 툴 설명과 스키마 힌트가 간결해졌다. 라우팅 가드레일은 유지.
- **의존성**: `@openclaw/proxyline` 0.3.3, Pi 패키지 0.75.1, Node.js 최소 지원 버전 22.19로 상향.

## 실무자가 볼 핵심 포인트

- **플러그인 개발자**: `openclaw plugins init`으로 시작해 `defineToolPlugin`으로 타입 안전한 툴을 선언하자. `validate`로 매니페스트 검증까지 한 번에 가능하다.
- **Python 개발자**: Python 디버거 스킬로 `debugpy` 원격 어태치 기반 에이전트 내 디버깅이 가능해졌다. 복잡한 파이프라인 디버깅에 바로 적용 가능.
- **브라우저 자동화**: 모달 다이얼로그가 `blockedByDialog`로 감지되고 `--dialog-id`로 처리 가능해졌다. 모달이 개입하는 웹 자동화 시나리오가 훨씬 안정적으로 작동한다.
- **인프라 운영자**: Docker 빌드 인수 이름이 변경됐다. `OPENCLAW_DOCKER_APT_PACKAGES`는 레거시 폴백으로 남지만 `OPENCLAW_IMAGE_APT_PACKAGES`로 전환을 권장한다.
- **QA 엔지니어**: `--runtime-parity-tier` 옵션으로 릴리스 체크 시 standard 티어와 soak/live-only 레인을 분리 관리할 수 있다.

---

*원문: [OpenClaw 2026.5.18 릴리스 노트](https://github.com/openclaw/openclaw/releases/tag/v2026.5.18) — GitHub*
