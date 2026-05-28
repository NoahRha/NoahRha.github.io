---
title: "OpenClaw v2026.5.26 릴리즈 — 트랜스크립트 통합·채널 안정화·보안 강화"
date: 2026-05-28T09:27:00+09:00
draft: false
description: "OpenClaw v2026.5.26이 출시됐다. Gateway 시작 최적화, 트랜스크립트 기반 단일 인프라, Telegram·iMessage·WhatsApp·Discord 채널 안정화, 리액션 승인, SSRF 보안 강화, OpenTelemetry LLM 스팬 등이 핵심이다."
tags: ["OpenClaw", "릴리즈", "AI에이전트", "Telegram", "멀티채널", "보안", "OpenTelemetry"]
cover:
  image: /images/openclaw-v2026-5-26-release-notes-cover.png
  alt: "OpenClaw v2026.5.26 릴리즈를 표현한 핸드드로잉 스타일 일러스트"
---

## 개요

OpenClaw v2026.5.26이 출시됐다. Gateway 시작 속도 개선, 트랜스크립트 기반 인프라 통합, 멀티채널 안정화, 보안 강화, 관찰 가능성 확대가 이번 릴리즈의 네 기둥이다. 특히 Telegram·iMessage·WhatsApp·Discord·Signal이 프로덕션 수준으로 격상됐고, 모바일에서 리액션 하나로 에이전트 작업을 승인할 수 있게 됐다.

---

## 핵심 요약

- **Gateway 시작 최적화**: 플러그인·채널·세션·파일시스템 중복 스캔 제거, 런타임 캐시 안정화
- **트랜스크립트 = 코어**: 미팅 요약·소스 청크·CLI 재생이 단일 트랜스크립트 경로로 통합
- **채널 프로덕션화**: Telegram 포럼 토픽, iMessage 첨부, WhatsApp 그룹, Discord 음성 모두 개선
- **리액션 승인**: Signal·iMessage·WhatsApp에서 엄지척 반응으로 `/approve` 대체
- **보안 강화**: SSRF 정책, 프롬프트 마커 스푸핑 차단, 외부 콘텐츠 래핑
- **OpenTelemetry LLM 스팬**: 도구 차단·페일오버·스테일 세션·페이로드 크기 알림 추가

---

## 본문

### Gateway: 시작 속도가 달라진다

이전에는 Gateway 시작 시 플러그인, 채널, 세션, 사용 비용, 경고, 스케줄드 서비스, 파일시스템을 반복 스캔했다. 이 중복 스캔을 제거하고 런타임·세션 캐시의 뒤집힘을 줄였다. 플러그인이 많은 환경에서 체감 차이가 크다.

가시적 답장(visible replies) 구조도 바뀌었다. 사용자에게 직접 전달되는 빠른 전송과 후속 처리 작업을 분리해 응답 지연을 낮췄다.

### 트랜스크립트: 흩어진 경로를 하나로

트랜스크립트 기반 미팅 요약, 소스 프로바이더 청크, 정제된 사용자 턴, 미디어 출처, Codex 미러, WebChat 답장, CLI/TUI 재생이 모두 단일 트랜스크립트 경로를 사용한다.

이전에는 기능마다 다른 데이터 경로를 탔다. 이번 통합으로 신뢰성과 일관성이 높아진다.

### 채널: 프로덕션 수준으로

채널별 개선이 이번 릴리즈의 가장 넓은 변경 영역이다.

**Telegram**: 타이핑·진행 상황 컨텍스트 유지, 포럼 토픽 지원이 추가됐다. 대형 그룹에서 대화 흐름 추적이 개선된다.

**iMessage**: 첨부 루트 처리, 원격 미디어 스테이징, 중복 로컬 Messages 소스 처리가 정리됐다.

**WhatsApp**: 그룹·미디어 동작이 복원됐다.

**Discord**: 음성 재생과 모델 선택이 개선됐다.

### 리액션 승인: 텍스트 없이 모바일에서 승인

Signal, iMessage, WhatsApp에 리액션 승인이 추가됐다. 텍스트 `/approve` 명령 없이 엄지척 반응 하나로 에이전트 작업을 승인한다. 이동 중에도 승인 플로우가 자연스러워진다.

### 음성과 Talk: 실시간 제어

Realtime Talk 실행을 Web UI와 Discord 음성에서 검사·조종·취소·후속 처리할 수 있게 됐다. 웨이크 네임 처리도 조정됐다. 주변 소리로 인한 실수 트리거를 줄이면서 실제 호출 반응은 유지한다.

### 보안: 콘텐츠 경계가 두텁다

- Browser 스냅샷 읽기에 SSRF 정책 적용
- 시스템 이벤트 텍스트의 중첩 프롬프트 마커 스푸핑 차단
- 가져온 파일 텍스트의 외부 콘텐츠 래핑
- ClickClack 인바운드 발신자 허용 목록이 에이전트 디스패치 전에 실행
- 만료된 디바이스 토큰 차단
- 직렬화된 도구 호출 텍스트 정리

### 프로바이더·Codex 안정화

명명된 인증 프로필로 Hermes, OpenCode, Codex 인증이 정리됐다. OpenAI 샘플링 파라미터가 Gateway를 통해 정상 전달된다. Codex 앱 서버의 재개·타임아웃·사용 한도 복구가 개선됐다.

### 관찰 가능성

Activity 탭, Gateway 시크릿 준비 트레이스, 도구·모델 스트림 진행 상황, 명시적 fast-mode 상태, systemd Gateway 위생, OpenTelemetry LLM 콘텐츠 스팬, 릴리즈 성능 증거, 풍부한 텔레메트리 신호가 추가됐다. 도구 차단·페일오버·스테일 세션·과대 페이로드·웹훅 인그레스에 대한 알림 가능 신호도 포함됐다.

### 설치·업데이트 경로

Alpine 설치, 신뢰할 수 있는 런타임 대체 루트, 안정적인 업데이트 채널, Docker/패키지 타임아웃, Windows Scheduled Tasks, macOS 러너 부트스트랩이 강화됐다.

---

## OpenClaw 사용자 체크리스트

- **리액션 승인 활성화 확인**: Signal·iMessage·WhatsApp에서 리액션 승인이 새로 동작한다. 모바일 승인 워크플로우를 쓴다면 테스트할 것.
- **Telegram 포럼 토픽**: 포럼 형식 그룹을 쓴다면 이번 릴리즈에서 지원이 추가됐다.
- **Browser 스냅샷 + SSRF**: Browser 스냅샷을 사용하는 에이전트가 있다면 SSRF 정책 변경 영향을 점검할 것.
- **OpenTelemetry 연동**: LLM 콘텐츠 스팬이 추가됐다. 기존 OTel 인프라가 있으면 연동해 에이전트 실행 가시성을 높일 수 있다.
- **Gateway 시작 시간**: 플러그인이 많은 환경에서 시작 속도가 체감적으로 개선된다.

---

## 원문 출처

- [openclaw v2026.5.26 릴리즈 노트 — GitHub](https://github.com/openclaw/openclaw/releases/tag/v2026.5.26)
