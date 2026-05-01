---
title: "OpenClaw 2026.4.29 업데이트: 메모리, 메시징, 게이트웨이 안정성 강화"
date: 2026-05-01T10:35:00+09:00
draft: false
description: "OpenClaw 2026.4.29 릴리스의 핵심 변경점을 한국어로 정리했다. 메시징 큐, Active Memory, NVIDIA provider, 게이트웨이 진단, 보안과 채널 안정성 개선을 중심으로 살펴본다."
tags:
  - OpenClaw
  - OpenClawRelease
  - AI에이전트
  - 메모리
  - 게이트웨이
  - 텔레그램
  - 보안
  - 릴리즈노트
categories:
  - OpenClaw
  - AI 에이전트
aliases:
  - /posts/openclaw-2026-4-29-release-update/
---

# OpenClaw 2026.4.29 업데이트: “오래 켜두고 쓰는 에이전트”에 가까워지다

OpenClaw 2026.4.29는 기능 하나가 크게 튀는 릴리스라기보다, 실제 운영 환경에서 자주 부딪히는 문제를 넓게 정리한 업데이트에 가깝습니다. 메시징 큐, 메모리, 모델 provider, 게이트웨이 시작 속도, 채널 안정성, 보안 정책까지 전반적으로 손봤습니다.

이번 버전의 핵심은 한마디로 **지속 실행성**입니다. 에이전트가 한 번 답하고 끝나는 도구가 아니라, 여러 채널에서 오래 켜져 있고, 중간에 사용자가 끼어들고, 기억을 불러오고, 서브에이전트를 돌리는 환경을 더 안정적으로 만드는 데 초점이 있습니다.

## 메시징과 후속 지시 처리 개선

가장 실사용에 가까운 변화는 메시징 큐입니다. 실행 중인 작업에 새 메시지가 들어왔을 때, 기본 동작이 `steer` 중심으로 정리되었습니다. 즉, 에이전트가 긴 작업을 하는 도중 들어온 후속 지시를 다음 모델 경계에서 더 자연스럽게 반영할 수 있게 된 것입니다.

또한 visible reply 관련 설정이 추가되어, 특정 채널에서는 보이는 답변이 반드시 메시지 전송 경로를 통해 나가도록 강제할 수 있습니다. 여러 채널을 함께 쓰는 운영자에게는 “답변이 생성됐는데 사용자에게 안 보이는” 상황을 줄이는 데 도움이 됩니다.

## 메모리는 사람 중심 위키에 가까워졌다

메모리 쪽 변화도 큽니다. 이번 릴리스에서는 사람 관련 메타데이터, 별칭, 관계 그래프, 출처와 증거 확인 흐름이 강화되었습니다. 단순히 과거 대화를 검색하는 수준을 넘어, “누구에 대한 기억인지”, “어떤 근거에서 나온 정보인지”를 더 잘 다룰 수 있게 되는 방향입니다.

Active Memory에는 대화별 허용·차단 필터가 추가되었습니다. 특정 DM이나 그룹에서는 기억을 쓰고, 다른 공간에서는 기억을 꺼두는 식의 제어가 가능해집니다. 개인정보와 맥락 분리가 중요한 환경에서는 꽤 중요한 개선입니다.

## NVIDIA provider와 모델 카탈로그 확장

모델 선택지도 넓어졌습니다. NVIDIA provider가 추가되어 NVIDIA 호스팅 모델을 provider prefix 그대로 선택할 수 있게 되었고, 모델 카탈로그와 인증 경로도 더 빠르게 정리되었습니다.

Bedrock의 Claude Opus 4.7 thinking profile 지원, OpenAI Codex 스트리밍·재생 안정화, OpenAI-compatible provider 처리 개선도 포함되었습니다. 여러 provider를 섞어 쓰는 사용자는 모델 전환과 인증 상태 확인에서 덜 흔들릴 가능성이 큽니다.

## 게이트웨이와 플러그인 안정성

게이트웨이 쪽은 느린 호스트와 패키지 설치 환경을 많이 의식한 업데이트입니다. 시작 단계 진단 타임라인, 이벤트 루프 readiness 진단, stale session 복구, 버전별 update cache, runtime dependency repair 등이 포함되었습니다.

특히 플러그인 runtime dependency 관련 수정이 많습니다. 컨테이너나 제한된 서버 환경에서 OpenClaw를 돌릴 때, 패키지 미러나 staging directory 문제로 게이트웨이가 반복적으로 깨지는 상황을 줄이려는 흐름입니다.

## 채널별 안정성: Telegram, Slack, Discord, WhatsApp

채널 관련 수정도 매우 많습니다. Telegram은 proxy, webhook, polling, quote reply, safe-send retry가 정리되었습니다. Slack은 Block Kit 제한을 넘는 버튼, select, approval 카드, 긴 fallback text를 더 안전하게 자릅니다.

Discord는 rate limit, startup, DM policy, session binding 쪽이 다듬어졌고, WhatsApp은 연결 liveness와 outbound message id 확인이 강화되었습니다. 여러 메신저를 한 에이전트에 붙여 운영하는 사람에게는 이런 작은 수정들이 체감 안정성으로 이어질 수 있습니다.

## 보안과 운영 정책 강화

보안 측면에서는 OpenGrep rulepack과 GitHub Code Scanning 연동, exec·pairing·owner scope 처리 강화, workspace PATH injection 방지, device pairing scope 검증, file-transfer preflight 강화 등이 들어갔습니다.

눈에 띄는 점은 “편하게 열어두는 설정”을 더 조심스럽게 다루는 방향입니다. 제한 프로필에서 `tools.exec`, `tools.fs` 설정이 암묵적으로 권한을 넓히지 않게 된 것도 같은 맥락입니다. 필요한 도구는 명시적으로 허용해야 합니다.

## 정리: 화려한 기능보다 운영 품질

OpenClaw 2026.4.29는 새 기능 발표라기보다 운영 품질 업데이트에 가깝습니다. 메시지를 중간에 더 잘 받아들이고, 기억을 더 안전하게 다루고, provider와 플러그인을 더 안정적으로 로딩하며, 메신저 채널의 자잘한 실패를 줄이는 방향입니다.

OpenClaw를 단순 CLI가 아니라 Telegram, Discord, Slack, 브라우저, 서브에이전트, 메모리까지 엮은 장기 실행 에이전트로 쓰고 있다면 이번 업데이트는 꽤 중요합니다. 겉으로 보이는 변화보다, “계속 켜두었을 때 덜 멈추는가”에 가까운 개선이 많기 때문입니다.

원문 : <a href="https://github.com/openclaw/openclaw/releases/tag/v2026.4.29">OpenClaw 2026.4.29</a>
