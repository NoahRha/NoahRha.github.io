---
title: "OpenClaw 2026.5.7 업데이트: Telegram·Discord·WhatsApp 안정성과 에이전트 컨텍스트 엔진 개선"
date: 2026-05-09T23:48:00+09:00
draft: false
description: "OpenClaw 2026.5.7은 Telegram/Discord/WhatsApp 메시징 안정성, 에이전트 컨텍스트 엔진 캐시 버그 수정, Cron CLI 상태 출력 개선, Codex OAuth 라우팅 보호 등 22명의 컨트리뷰터가 참여한 집중 버그픽스 릴리스다."
cover:
  image: "/images/openclaw-v2026-5-7-cover.png"
  alt: "OpenClaw v2026.5.7 릴리스 — 멀티플랫폼 메시징 안정성과 에이전트 컨텍스트 개선"
  caption: ""
tags:
  - OpenClaw
  - 릴리스노트
  - AI에이전트
  - Telegram
  - Discord
  - 업데이트
categories:
  - OpenClaw
---

OpenClaw 2026.5.7이 출시됐다. 새 기능보다 **안정성과 신뢰성에 집중한 버그픽스 릴리스**로, 22명의 컨트리뷰터가 메시징 플랫폼, 에이전트 엔진, CLI 도구 전반의 크고 작은 문제를 정리했다.

---

## 핵심 요약

- **Telegram/Discord/WhatsApp** 메시징 라우팅, 폴링 안정성, 음성 캡처 품질 개선
- **에이전트 컨텍스트 엔진**: 리셋 후 이전 히스토리가 재사용되던 캐시 버그 수정
- **Cron CLI**: `--json` 출력에 `disabled/running/ok/error/skipped/idle` 상태 포함
- **Channels CLI** 전면 정비: 채널 목록 분리, 설치/설정/활성화 상태 표시
- **Codex OAuth**: `doctor --fix` 실행 시 작동 중인 openai-codex/* 라우트 보호
- 보안: Active Memory 전역 토글에 admin 권한 필요, 자동 응답 툴 실행에 인가 훅 적용

---

## 에이전트 & 컨텍스트 엔진

### 컨텍스트 캐시 버그 수정

가장 영향 범위가 넓은 수정이다. 에이전트 컨텍스트 엔진이 소스 히스토리가 줄어들거나 어셈블리가 실패할 때 캐시된 컨텍스트 뷰를 무효화하지 않는 문제가 있었다. `/new`나 `sessions.reset` 이후에도 리셋 전 히스토리가 컨텍스트로 재사용되는 현상이 여기서 비롯됐다.

- **`/new`, `sessions.reset` 시 스킬 스냅샷 캐시 초기화** — 장기 실행 채널 세션에서 스킬이 변경된 후 목록이 갱신되지 않던 문제 해결
- **서브에이전트 보관 TTL** 하드코딩된 5분 대신 `agents.defaults.subagents.archiveAfterMinutes` 설정값을 따르도록 수정

### 에이전트 컴팩션 토큰 제한

컴팩션 요약 예약 토큰이 모델 출력 한도를 초과해 잘못된 `max_tokens` 값이 요청되는 문제를 수정했다. 고컨텍스트 컴팩션에서 API 오류가 발생하던 케이스가 이에 해당한다.

---

## Telegram 안정성 대거 개선

### 폴링 감시 강화

`getUpdates` 활성 상태에 폴링 감시 프로세스를 연결하도록 변경했다. 이전에는 무관한 Bot API 아웃바운드 호출이 인바운드 폴러 중단을 감추는 현상이 있었다.

### 접근 그룹 허용 목록 수정

`accessGroup:*` 발신자 허용 목록이 DM, 그룹, 네이티브 커맨드, 콜백 인가에 제대로 적용되지 않던 문제를 수정했다. Telegram 숫자 발신자 ID 검사 이전에 허용 목록 검사가 먼저 이루어진다.

### 아웃바운드 메시지 처리 개선

- 동일 채팅 내에서 인바운드 턴 도중 툴 아웃바운드 전송이 성공하면 전달된 것으로 처리 — 불필요한 조용한 폴백 응답 방지
- `/models` 콜백 버튼에서 점(`.`)을 포함한 프로바이더 ID 파싱 개선 (예: `hf.co` 모델 목록)

---

## Discord 개선

### 음성 캡처 품질 향상

Discord 음성 채널 사용 품질이 크게 개선됐다.

- 발화 후 묵음 처리 대기 시간을 기본 **2.5초**로 연장 (끊김 현상 감소)
- 시끄러운 Discord 세션을 위한 `voice.captureSilenceGraceMs` 설정 추가
- 라이브 STT 프래그먼트 주변의 음성 출력 프롬프트 정밀화

### 음성 권한 감사

`channels capabilities`와 `channels status --probe`에서 Discord 음성 채널 권한 감사 기능이 추가됐다. `/vc join` 실행 전에 Connect/Speak/Read Message History 권한 누락을 사전에 확인할 수 있다.

### 메시지 라우팅 수정

`discord:channel:` 형태의 프로바이더 접두사 타겟을 채널 전송으로 올바르게 파싱하도록 수정했다. 이전에는 채널 ID가 레거시 Discord DM 타겟으로 잘못 라우팅되어 "Unknown Channel" 오류가 발생했다.

---

## WhatsApp 개선

### LID 주소 라우팅

LID 주소 연락처에 에이전트 메시지가 발신자 전용 고스트 채팅을 생성하는 대신 정상 전달되도록 Baileys LID 포워드 매핑을 통한 라우팅을 구현했다.

### 미디어 캡션 중복 전송 수정

`MEDIA:` 디렉티브 자동 응답이 빈 미디어 메시지를 먼저 보낸 뒤 캡션 미디어를 다시 보내던 문제를 수정했다. 이제 캡션 포함 미디어가 한 번만 전송된다.

---

## Cron & 스케줄러

### CLI JSON 출력 상태 포함

`cron list --json`과 `cron show --json` 출력에 계산된 상태값이 포함된다. 외부 툴링에서 `disabled`, `running`, `ok`, `error`, `skipped`, `idle` 상태를 직접 읽을 수 있어 별도 상태 로직 구현이 불필요해졌다.

### 잘못된 모델 오버라이드 수정

`payload.model`이 `"default"`, `"null"`, 빈 문자열, JSON null로 저장된 크론 잡을 `openclaw doctor --fix`가 자동으로 수정한다. 크론 런타임 모델 유효성 검사는 그대로 유지된다.

### 격리 실행 전 전달 실패 처리

`delivery.channel=last`에 이전 라우트가 없는 경우, 모델 실행 전에 announce delivery가 먼저 실패하도록 변경했다. 반복 잡이 영구적인 전달 타겟 오류에 도달하기 전에 불필요하게 토큰을 소비하지 않는다.

---

## Channels CLI 전면 정비

`openclaw channels list`가 채널 전용으로 변경됐다. 주요 변경 사항:

- `--all` 플래그로 번들 및 카탈로그 채널 포함
- 설치/설정/활성화 상태 렌더링
- 모델 인증·사용 상세는 `openclaw models auth list`, `openclaw status`, `openclaw models list`로 이동

---

## 보안 강화

- **Active Memory 전역 토글**: admin 권한 필요하도록 변경
- **자동 응답 인라인 스킬 툴**: `before-tool-call` 인가 훅을 통해 실행
- **네이티브 커맨드**: owner 강제 적용
- **Tavily**: 활성 런타임 설정 스냅샷에서 전용 자격 증명 확인 (`SecretRef` 기반 API 키 미해결 전달 방지)

---

## Codex & 모델 프로바이더

### OpenAI chat-latest 지원

`openai/chat-latest`를 직접 API-키 모델 오버라이드로 지정할 수 있다. 기본 안정 모델을 변경하지 않고 ChatGPT Instant API 별칭을 시험해볼 수 있다.

### Codex OAuth 라우트 보호

`doctor --fix` 실행 시 작동 중인 `openai-codex/*` PI 라우트를 보존하도록 개선됐다. 2026.5.5에서 재작성된 `openai/*` GPT-5 라우트도 Codex OAuth 인증만 있는 경우 복구된다.

### 모델 프로바이더 기타 수정

- APNG → PNG 정규화
- Gemini 3 툴 콜 thought-signature 리플레이 보존 (폴백 시그니처 포함)
- 레거시 `__env__:VAR` 커스텀 프로바이더 키 수용
- snake_case 툴 콜 트랜스크립트 새니타이제이션 수정

---

## 플러그인 & 설치

- **ClawHub 퍼블리싱**: 일시적 CLI 의존성 설치 실패 재시도, 프리뷰 통과 플러그인 게시 가능 유지, 퍼블리시 후 예상 패키지 버전 검증
- **플러그인 설치/언인스톨**: 절대 POSIX npm 쉘 사용으로 제한된 PATH 환경에서의 정리 실패 방지
- **외부 플러그인 채널 설정**: `setChannelRuntime`을 비번들 외부 플러그인 설정 항목에서 포워딩

---

## 컨트리뷰터

이번 릴리스에는 **22명**이 기여했다.

vincentkoc, aweiker, VACInc, manugc, arniesaha, Evizero, sallyom, joeyfrasier, sliverp, zerone0x, bizzle12368239, openperf, nailujac, edenfunf, shakkernerd, ai-hpc, RajvardhanPatil07, adzendo, brokemac79, neeravmakwana, ChrisBot2026, pgondhi987

---

*원문 출처: [OpenClaw v2026.5.7 릴리스 노트](https://github.com/openclaw/openclaw/releases/tag/v2026.5.7)*
