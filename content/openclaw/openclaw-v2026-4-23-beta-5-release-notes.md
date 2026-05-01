---
title: "OpenClaw 2026.4.23 beta 5 업데이트: Codex OAuth 이미지 생성과 OpenRouter 지원 강화"
date: 2026-04-24T23:14:00+09:00
draft: false
description: "OpenClaw 2026.4.23 beta 5는 Codex OAuth 기반 이미지 생성, OpenRouter image_generate, subagent 문맥 제어, 미디어 지속성, 보안 하드닝을 강화한 릴리스다."
cover:
  image: "/images/openclaw-v2026-4-23-beta-5-cover.jpg"
  alt: "OpenClaw 2026.4.23 beta 5 릴리스의 이미지 생성, 라우팅, 운영 워크플로우 개선을 표현한 대표 이미지"
  caption: ""
tags:
  - OpenClaw
  - OpenClawRelease
  - AI에이전트
  - CodexOAuth
  - OpenRouter
  - ImageGenerate
  - 릴리즈노트
categories:
  - OpenClaw
  - AI 에이전트
aliases:
  - /posts/openclaw-v2026-4-23-beta-5-release-notes/
---

# OpenClaw 2026.4.23 beta 5 업데이트: Codex OAuth 이미지 생성과 OpenRouter 지원 강화

![OpenClaw 2026.4.23 beta 5 대표 이미지](/images/openclaw-v2026-4-23-beta-5-cover.jpg)


OpenClaw 2026.4.23 beta 5가 공개됐습니다. 이번 OpenClaw release는 단순한 버그 수정 묶음이라기보다, AI agent를 실제로 운영하는 사람들이 자주 부딪히는 문제를 꽤 폭넓게 정리한 업데이트에 가깝습니다.

가장 큰 변화는 이미지 생성입니다. 구성된 Codex OAuth 또는 `openai-codex` 프로필이 활성화된 환경에서는 `openai/gpt-image-2`를 별도의 `OPENAI_API_KEY` 없이 사용할 수 있고, OpenRouter 이미지 모델도 `image_generate` 도구 안으로 들어왔습니다.

여기에 로컬 메모리 검색의 VRAM 부담을 낮추는 설정, subagent 세션 문맥 제어, 생성 도구별 timeout, WebChat과 Control UI의 미디어 지속성, 여러 채널의 보안 하드닝까지 함께 포함됐습니다.

베타 릴리스이긴 하지만 방향성은 분명합니다. OpenClaw는 “AI와 대화하는 도구”를 넘어 provider routing, memory, media generation, messaging surface, harness orchestration을 묶는 운영형 AI 에이전트 플랫폼으로 다듬어지고 있습니다.

## 이번 릴리스의 핵심은 이미지 생성 워크플로우다

OpenClaw v2026.4.23-beta.5에서 가장 먼저 봐야 할 부분은 이미지 생성과 편집 경로입니다.

이번 버전부터 Providers/OpenAI 쪽에서 Codex OAuth를 통한 이미지 생성 및 참조 이미지 편집이 추가됐습니다. 그래서 `openai/gpt-image-2`를 사용할 때, 구성된 Codex OAuth 경로가 있는 환경에서는 별도의 `OPENAI_API_KEY` 없이도 이미지 생성 기능을 쓸 수 있습니다.

OpenClaw 사용자 입장에서는 이 변화가 작지 않습니다. 이미지 생성은 이제 단순히 “모델 하나 호출하기”가 아니라, 에이전트가 작업 중 필요한 시점에 썸네일을 만들고, 참조 이미지를 편집하고, 결과물을 채팅 표면이나 웹 UI에 다시 전달하는 하나의 workflow입니다. 인증 경로가 줄어들면 그만큼 설정 부담도 줄어듭니다.

특히 블로그 썸네일, SNS 카드뉴스, 제품 목업, 설명용 다이어그램처럼 반복 생성이 필요한 콘텐츠 작업에서 체감이 클 수 있습니다.

## OpenRouter 이미지 모델도 image_generate 안으로 들어왔다

두 번째 큰 변화는 OpenRouter 지원입니다. 이번 릴리스는 Providers/OpenRouter에 이미지 생성 및 참조 이미지 편집을 추가했습니다. 즉 `OPENROUTER_API_KEY`를 설정한 사용자는 OpenRouter 이미지 모델을 OpenClaw의 `image_generate` 흐름에서 사용할 수 있습니다.

관련 PR인 #67668 설명을 보면, OpenRouter의 OpenAI-compatible `/chat/completions` endpoint를 활용하고, `modalities: ["image", "text"]` 방식의 이미지 출력을 처리합니다. 또한 generate와 edit 모드, 여러 aspect ratio, 1K/2K/4K resolution hint, OpenRouter의 비표준 이미지 응답 포맷 파싱까지 포함되어 있습니다.

이건 단순 연동보다 의미가 큽니다. OpenClaw 업데이트가 향하는 방향은 provider를 하나로 고정하는 것이 아니라, 여러 이미지 모델을 같은 도구 인터페이스 안에서 선택하고 라우팅하는 쪽에 가깝습니다.

운영자 관점에서는 작업에 따라 속도, 비용, 품질 특성이 다른 모델을 선택하는 전략을 세울 수 있습니다. AI 이미지 생성이 실험이 아니라 콘텐츠 생산 파이프라인이 되려면 이런 선택권이 중요합니다.

## image_generate 옵션이 더 실전적으로 바뀌었다

이번 OpenClaw release notes에는 `image_generate` 도구의 옵션 확장도 포함되어 있습니다. 에이전트가 provider-supported `quality`와 `outputFormat` hint를 요청할 수 있고, OpenAI 전용으로 background, moderation, compression, user hint도 전달할 수 있습니다.

PR #70503은 이 변경의 배경을 잘 보여줍니다. `gpt-image-2`를 실제 운영에서 쓰려면 단순히 이미지를 만들 수 있는지만으로는 부족합니다. 빠른 초안 생성을 위해 낮은 quality를 쓰거나, 웹 업로드에 맞춰 jpeg/webp를 고르거나, 투명 배경이 필요한 에셋을 만들거나, 압축률을 조정해야 할 때가 있습니다.

작아 보이는 옵션이지만, 자동화에서는 큰 차이를 만듭니다. 사람이 한 번 클릭해서 이미지를 만드는 상황과, agent workflow가 수십 번 반복 호출하는 상황은 다릅니다. 이 옵션 확장은 OpenClaw image_generate를 좀 더 생산 환경에 맞게 다듬는 변화로 볼 수 있습니다.

## subagent 문맥 공유: 기본은 격리, 필요할 때만 fork

Agents/subagents 쪽에서는 native `sessions_spawn` 실행에 optional forked context가 추가됐습니다. 핵심은 기본값이 여전히 clean isolated session이라는 점입니다.

OpenClaw에서 subagent를 자주 쓰는 사람이라면 이 차이를 바로 이해할 수 있습니다. 모든 하위 에이전트가 부모 대화 전체를 자동으로 물려받으면 편할 수는 있지만, 보안·프라이버시·토큰 비용·맥락 오염 문제가 생깁니다. 반대로 항상 완전 격리만 하면 현재 대화 맥락이 필요한 작업에서 효율이 떨어집니다.

이번 변경은 그 중간 지점을 제공합니다.

- 기본값은 안전한 isolated session
- 필요한 경우에만 forked context 명시
- 문맥 상속 여부를 작업 단위로 제어

AI agent workflow를 여러 specialist agent로 나누어 운영하는 사용자에게는 꽤 중요한 개선입니다.

## 생성 도구마다 timeoutMs를 따로 줄 수 있다

이미지, 비디오, 음악, TTS generation tools에는 per-call `timeoutMs` 지원이 추가됐습니다.

생성형 AI 도구는 응답 시간이 일정하지 않습니다. 이미지 한 장은 빠르게 나올 수 있지만, 고품질 이미지 편집이나 비디오 생성, 음악 생성은 provider 상태와 요청 복잡도에 따라 오래 걸릴 수 있습니다. 이제 OpenClaw agent는 특정 generation call에만 timeout을 길게 줄 수 있습니다.

예를 들어 채팅 응답용 이미지는 짧게 제한하고, 백그라운드용 고품질 이미지 생성은 더 오래 기다리게 만들 수 있습니다. 운영자 관점에서는 전체 시스템 timeout을 무리하게 늘리지 않고도, 오래 걸리는 호출만 예외적으로 다룰 수 있다는 점이 좋습니다.

## 로컬 메모리 검색의 VRAM 부담을 낮춘 contextSize 4096

Memory/local embeddings 쪽에서는 `memorySearch.local.contextSize` 설정이 추가됐고, 기본값은 4096입니다.

PR #70544에 따르면 이 변경의 배경은 로컬 임베딩 모델의 VRAM 사용량입니다. 예를 들어 Qwen3-Embedding-8B 같은 큰 임베딩 모델에서 context size를 `auto`로 두면 모델의 학습 컨텍스트에 맞춰 훨씬 큰 메모리를 잡을 수 있고, 제한된 GPU 환경에서는 OOM으로 이어질 수 있습니다.

OpenClaw의 memory search는 장기 기억과 프로젝트 문맥을 다루는 핵심 기능입니다. 하지만 로컬 환경에서 돌리는 사용자에게는 안정성이 더 중요합니다. 기본값 4096은 일반적인 memory-search chunk에는 충분하면서도, 과도한 VRAM 사용을 피하는 현실적인 선택으로 해석할 수 있습니다.

필요한 사용자는 `memorySearch.local.contextSize`를 직접 조정할 수 있고, 리소스가 제한된 호스트에서는 환경에 맞게 더 낮은 값으로 조정하는 선택지도 생깁니다.

## Codex harness는 더 조용하게, 하지만 더 잘 보이게

Codex harness에는 structured debug logging이 추가됐습니다. PR #70760의 핵심은 `/status`는 단순하게 유지하면서, gateway logs에는 harness 선택 이유와 fallback 판단을 구조화해서 남기는 것입니다.

좋은 운영 도구는 평소에는 조용해야 합니다. 하지만 문제가 생겼을 때는 “왜 이 harness가 선택됐는지”, “왜 Pi fallback이 일어났는지”, “어떤 후보가 지원되지 않았는지”를 추적할 수 있어야 합니다.

이번 변경은 바로 그 관찰성 개선입니다. OpenClaw를 장시간 켜두고 Codex harness, Pi, subagent runs를 함께 쓰는 운영자라면 디버깅 피로도가 줄어들 가능성이 큽니다.

## WebChat, Control UI, 미디어 지속성도 개선됐다

이번 릴리스에는 이미지와 미디어 관련 fix가 유난히 많습니다.

Gateway/WebChat은 text-only primary model을 쓰는 경우에도 이미지 첨부를 media ref로 보존해, 설정된 이미지 도구가 원본 파일을 검사할 수 있게 했습니다. Media understanding 쪽에서는 명시적인 image-model 설정을 우선하도록 개선됐고, Codex image models를 통한 bounded image turn도 지원합니다.

Control UI/chat에서는 assistant-generated images를 authenticated managed media로 저장하고, paired-device token으로 media fetch를 허용하는 수정이 들어갔습니다. PR #70719는 이 변경의 의미를 잘 설명합니다. 생성된 이미지가 실시간 화면에서는 보였지만, chat history reload 후 사라지는 문제를 관리형 미디어 저장 방식으로 해결한 것입니다.

콘텐츠 제작자에게 이건 꽤 중요합니다. 생성된 이미지는 채팅 부산물이 아니라 결과물입니다. 새로고침 후 사라지면 workflow를 신뢰하기 어렵습니다. 이번 개선은 OpenClaw를 콘텐츠 제작 도구로 쓰는 사용자에게 특히 반가운 변화입니다.

## memory CLI와 MEMORY.md 처리도 안정화

Memory/CLI 쪽에서는 built-in `local` embedding provider가 memory-core manifest에 선언되어, standalone `openclaw memory status`, `index`, `search`가 gateway runtime처럼 local embeddings를 찾을 수 있게 됐습니다. PR #70873은 이 문제가 v2026.4.22에서 local memory CLI 사용자에게 실제 regression으로 나타났다고 설명합니다.

또한 Memory/doctor는 root durable memory를 `MEMORY.md`로 canonicalize하고, lowercase `memory.md`를 runtime fallback으로 취급하지 않도록 정리했습니다. `openclaw doctor --fix`가 split-brain root files를 백업과 함께 병합할 수 있게 된 점도 운영자에게 유용합니다.

OpenClaw에서 메모리는 agent의 장기 문맥입니다. 따라서 CLI, gateway, doctor가 같은 기준으로 memory를 바라보는 것은 안정적인 AI 에이전트 운영의 기본입니다.

## 메시징 채널과 보안 하드닝: 작지만 중요한 수정들

이번 v2026.4.23-beta.5에는 Telegram, WhatsApp, Slack, Discord, Google Meet 등 채널 관련 수정도 많습니다.

예를 들어 Telegram media replies는 markdown image syntax를 outbound media payload로 파싱해, 그룹 채팅에서 이미지 URL이 평문으로 떨어지는 문제를 줄였습니다. Slack에서는 MPIM group DM을 group chat context로 분류하고, non-DM surface에서 verbose tool/plan progress가 새어 나가지 않도록 했습니다. WhatsApp은 onboarding과 outbound media normalization 관련 수정이 포함됐습니다.

보안 하드닝도 넓게 들어갔습니다. 릴리즈 노트 기준으로 보면 다음 항목들이 특히 눈에 띕니다.

- QQBot `/bot-approve`에 framework auth 요구
- MCP tools bridge에서 owner-only tool 노출 및 호출 차단
- Webhooks SecretRef route secret을 요청마다 다시 해석해 secret reload 반영
- Gateway `config.apply` / `config.patch` runtime edit 경계를 allowlist 방식으로 강화
- WhatsApp contact, vCard, location metadata를 inline body가 아닌 fenced untrusted metadata JSON으로 렌더링
- Group chat 이름과 participant label을 inline prompt가 아닌 untrusted metadata JSON으로 렌더링
- file-backed secret 및 ACL 관련 경계 강화

이 항목들은 화려한 기능은 아니지만, OpenClaw를 외부 채널과 연결해 운영하는 사람에게는 매우 중요합니다. AI agent 운영에서는 “무엇을 할 수 있는가”만큼 “무엇을 함부로 하지 않게 막는가”가 중요하기 때문입니다.

## 그 밖의 개발자 경험 개선

Dependencies/Pi는 bundled Pi packages를 0.70.0으로 업데이트했고, OpenAI와 OpenAI Codex에 대해 Pi의 upstream `gpt-5.5` catalog metadata를 사용하도록 조정했습니다.

Codex harness/Windows는 npm-installed `codex.cmd` shim을 PATHEXT를 통해 해석해, Windows에서 `codex/*` models가 수동 `.exe` shim 없이 동작하도록 수정했습니다. Agents/WebChat은 billing, auth, rate-limit 같은 non-retryable provider failure를 WebChat에 제대로 표시하도록 개선했습니다.

또한 Block streaming duplicate reply 방지, replay 처리, context-engine assembly failure redaction, Stop-button abort queueing, Claude CLI prompt-build hook 적용 등 운영 중 마찰을 줄이는 수정들이 함께 포함됐습니다.

## 이번 OpenClaw 업데이트를 어떻게 봐야 할까

OpenClaw 2026.4.23 beta 5는 “이미지 생성이 좋아졌다”로만 요약하기에는 범위가 넓습니다. 물론 Codex OAuth 기반 `gpt-image-2`, OpenRouter image provider, `image_generate` 옵션 확장은 이번 릴리스의 가장 눈에 띄는 변화입니다.

하지만 진짜 메시지는 조금 더 운영 쪽에 있습니다.

OpenClaw는 여러 provider, 여러 채널, 여러 agent, 여러 media artifact를 한 시스템 안에서 다룹니다. 그런 시스템에서는 인증, 라우팅, 메모리, 미디어 저장, timeout, 보안 경계, 로그 관찰성이 모두 중요합니다.

이번 릴리스는 그 연결부를 상당히 많이 다듬었습니다. 베타 버전인 만큼 운영 환경에 바로 적용한다면 사전 테스트가 필요하지만, OpenClaw를 AI 에이전트 운영 플랫폼으로 쓰는 사용자라면 확인할 가치가 큰 업데이트입니다.

원문 : <a href="https://github.com/openclaw/openclaw/releases/tag/v2026.4.23-beta.5">OpenClaw 2026.4.23 beta 5</a>
