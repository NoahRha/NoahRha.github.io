---
title: "OpenClaw 2026.5.12: 런타임 의존성 분리, Telegram 안정성, 보안 강화"
date: 2026-05-16T15:10:00+09:00
draft: false
description: "OpenClaw 2026.5.12 핵심 변경점 한국어 정리. AWS/Slack/Vertex 의존성 코어 분리로 설치가 가벼워졌고, Telegram 폴링이 격리 워커로 분리됐다. 보안·플러그인·UI 전반에 걸친 개선 내용을 살펴본다."
tags:
  - OpenClaw
  - OpenClawRelease
  - AI에이전트
  - 플러그인
  - Telegram
  - 게이트웨이
  - 릴리즈노트
categories:
  - OpenClaw
  - AI 에이전트
aliases:
  - /posts/openclaw-2026-5-12-release-update/
cover:
  image: /images/openclaw-2026-5-12-release-cover.png
  alt: "OpenClaw 2026.5.12 release — runtime dependency separation and Telegram resilience"
  caption: "Generated illustration"
---

## 개요

OpenClaw 2026.5.12가 2026년 5월 14일 릴리스됐다. 이번 버전의 핵심은 세 가지다. 첫째, 코어 런타임에서 대형 공급자 의존성을 분리해 설치가 가벼워졌다. 둘째, Telegram 폴링이 격리 워커로 분리되며 이벤트 루프 정지에도 메시지를 놓치지 않게 됐다. 셋째, 보안·인증·플러그인 경로 전반에 걸쳐 광범위한 하드닝이 들어갔다.

## 핵심 요약

- **런타임 의존성 분리**: Amazon Bedrock, Anthropic Vertex, Slack, WhatsApp이 코어에서 빠져 설치 시 필요한 것만 당긴다
- **Telegram 격리 폴링**: 이벤트 루프 정지와 무관하게 수신이 유지되는 독립 워커 + 로컬 스풀링
- **ACP 폴백**: 기본 런타임 백엔드가 죽어도 설정된 백업 백엔드로 자동 전환
- **보안 강화**: 프로바이더 env-var 추론 방식 변경, Windows USERPROFILE 샌드박스 차단, macOS TLS 신뢰 강제
- **auto-scroll 모드 선택기**: Control UI/WebChat에서 스트리밍 스크롤 동작을 사용자가 직접 선택
- **세션 분류 수정**: ACP spawn-child 세션이 `kind: "direct"` 대신 `kind: "spawn-child"`로 올바르게 표시

## 런타임 의존성 분리: 코어가 가벼워졌다

이번 릴리스에서 가장 실용적인 변화다. 기존에는 OpenClaw를 설치하면 실제로 사용하지 않아도 Amazon Bedrock의 AWS SDK, Anthropic Vertex, Slack 클라이언트 등 대형 의존성이 함께 설치됐다. 이제 각 공급자 패키지는 해당 플러그인을 설치할 때만 당겨진다.

구체적으로 분리된 항목은 다음과 같다.

- Amazon Bedrock / Bedrock Mantle 프로바이더 패키지
- Slack, OpenShell 샌드박스, Anthropic Vertex 플러그인

Bedrock을 쓰지 않는 환경이라면 AWS SDK 전체를 설치하지 않아도 된다. 설치 속도와 디스크 사용량이 눈에 띄게 달라진다.

## Telegram: 격리 워커와 내구성 스풀링

Telegram 채널은 이번 릴리스에서 세 가지 핵심 수정을 받았다.

**격리 폴링 워커**: 기존 Telegram Bot API 폴링은 메인 이벤트 루프 안에서 돌았다. 이벤트 루프가 무거운 작업으로 막히면 폴링도 멈췄다. 이제 폴링은 독립 워커로 분리되고, 수신된 메시지는 내구성 로컬 스풀에 먼저 저장된다. 처리 쪽이 느려져도 메시지를 잃지 않는다.

**HTML 포맷 보존**: 크론으로 예약된 응답이나 lazy deliver 경로에서 Markdown 링크가 텍스트로 깨지는 버그가 수정됐다. 링크가 클릭 가능한 앵커 태그로 제대로 전달된다.

**그룹 미디어 필터링**: `requireMention`이 켜진 그룹에서 언급되지 않은 미디어 메시지에도 다운로드를 시도하던 버그가 수정됐다. 이제 언급 없는 메시지는 다운로드 자체를 건너뛴다.

## ACP 폴백과 세션 분류

**ACP 폴백**: 새로운 `acp.fallbacks` 옵션으로 ACP 턴이 기본 런타임 백엔드를 쓸 수 없을 때 설정된 백업 백엔드를 순서대로 시도한다. 출력이 전혀 나오기 전에 폴백이 일어나므로 사용자 입장에서는 오류 없이 처리된다.

**세션 분류 수정**: ACP spawn-child 세션이 `openclaw sessions`와 `openclaw status`에서 `kind: "direct"`로 잘못 표시되던 문제가 수정됐다. 이제 `kind: "spawn-child"`로 정확히 분류되며, 중복 분류 로직은 `src/sessions/classify-session-kind.ts`로 통합됐다.

## 보안 하드닝

이번 릴리스는 여러 경로의 보안을 강화했다.

**프로바이더 env-var 추론 변경**: 기존에는 대문자 환경 변수명(`^[A-Z_][A-Z0-9_]*$`)을 광범위하게 프로바이더 자격증명 후보로 추론했다. 이 방식은 무관한 환경 변수가 우발적으로 API 키로 인식될 수 있었다. 이제 구조화된 `secrets.providers[id]` / `secrets.defaults` SecretRef만 프로바이더 apiKey로 사용된다.

**Windows 샌드박스**: Windows에서 `USERPROFILE` 경로가 샌드박스 차단 홈 루트에 추가됐다. `HOME`이 다른 쉘 홈을 가리키는 환경에서도 `.codex`, `.openclaw`, `.ssh` 같은 자격증명 경로가 차단된다.

**macOS TLS 신뢰**: 직접 wss:// 게이트웨이 인증서를 처음 고정(pin)하기 전에 시스템 TLS 신뢰를 먼저 확인하도록 변경됐다. 신뢰할 수 없는 인증서는 대역 외 설정 없이는 연결에 실패한다.

**인증 잠금 파일 복구**: OAuth 갱신이 비정상 종료되면 `auth-profiles.json` 쓰기 잠금이 남아 수동 삭제가 필요했다. 이제 죽은 프로세스의 스테일 파일 잠금을 먼저 회수한 뒤 재시도한다.

## UI 개선: auto-scroll 모드 선택기

Control UI와 WebChat에 스트리밍 스크롤 모드 선택기가 추가됐다. 세 가지 모드를 제공한다.

- **near-bottom**: 기존 동작과 동일. 화면 하단 근처에 있을 때만 자동 스크롤
- **always**: 스트리밍 출력을 항상 따라간다
- **off**: 자동 스크롤을 끄고 "새 메시지" 버튼으로 수동 이동

긴 스트리밍 응답을 읽는 중에 화면이 갑자기 내려가는 불편함을 없애준다.

## 플러그인 관련 수정

pnpm 11 지원이 추가됐다. 플러그인 설치 시 피어 의존성이 보존되고, 소스/git 설치 경로의 버그도 수정됐다. 플러그인 SDK에서 deprecated된 `openclaw/plugin-sdk/memory-core` 서브패스가 `memory-host-core`의 별칭으로 복원됐다. 기존에 발행된 메모리 컴패니언 플러그인이 현재 호스트에서도 정상 동작한다.

## 실무자가 볼 핵심 포인트

1. **Bedrock/Vertex를 안 쓰면 지금 당장 이득이다** — 코어 재설치 후 AWS SDK가 없어지고 설치가 빨라진다. CI 환경이나 Docker 이미지에서 효과가 크다
2. **Telegram 봇을 길게 켜두는 환경은 업데이트 권장** — 이벤트 루프 정지로 메시지를 잃는 버그가 구조적으로 해결됐다
3. **env-var 기반 프로바이더 자격증명 구성을 재확인하라** — 추론 방식이 바뀌어 기존 환경 변수 기반 설정이 작동하지 않을 수 있다. `secrets.providers[id]` 구조로 명시적으로 지정해야 한다
4. **Windows 배포 환경은 샌드박스 경로 재점검** — USERPROFILE 차단이 추가됐으므로 기존에 USERPROFILE 경로를 활용하던 설정이 있다면 확인이 필요하다
5. **ACP 폴백 설정으로 다운타임 대응** — `acp.fallbacks`에 백업 런타임을 설정해두면 기본 백엔드 장애 시 자동 전환된다

## 원문 출처

*원문: [openclaw 2026.5.12 — GitHub openclaw/openclaw Releases (2026. 5. 14)](https://github.com/openclaw/openclaw/releases/tag/v2026.5.12)*
