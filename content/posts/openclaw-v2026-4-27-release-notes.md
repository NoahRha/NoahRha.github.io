---
title: "OpenClaw 2026.4.27 업데이트: Codex Computer Use와 DeepInfra, 그리고 운영 안정성 개선"
date: 2026-04-30T17:45:00+09:00
draft: false
tags:
  - OpenClaw
  - ReleaseNotes
  - Codex
  - DeepInfra
  - Telegram
  - Slack
  - PluginSDK
  - Gateway
categories:
  - 기술문서
  - 릴리스해설
---

## 핵심 요약

OpenClaw 2026.4.27은 화려한 신기능 하나보다, 실제 운영자가 자주 부딪히는 지점을 넓게 다듬은 릴리스에 가깝습니다. Codex Computer Use 설정이 정식 흐름으로 들어왔고, DeepInfra가 기본 provider 세트에 합류했으며, Tencent Yuanbao와 QQBot 쪽 채널 지원도 넓어졌습니다. 동시에 Telegram, Slack, Gateway 시작 속도, 플러그인 런타임, 세션/메모리/크론 안정성까지 꽤 많은 보완이 들어갔습니다.

## Codex Computer Use 설정이 훨씬 명확해졌다

이번 릴리스에서 가장 눈에 띄는 변화는 Codex Computer Use입니다. 이제 Codex 모드에서 데스크톱 제어를 쓰기 위한 상태 확인, 설치 명령, marketplace discovery, MCP 서버 점검 흐름이 함께 제공됩니다.

예전에는 “Codex로 Computer Use를 쓰려면 무엇이 준비되어 있어야 하는지”가 다소 흩어져 있었다면, 이번에는 설정 단계에서 필요한 요소를 더 분명하게 확인할 수 있게 됐습니다. 특히 MCP 서버 체크가 fail-closed 방식으로 들어간 점이 좋습니다. 애매하게 시작했다가 중간에 깨지는 것보다, 준비가 안 됐으면 처음부터 막아주는 쪽이 운영에는 훨씬 안전합니다.

## DeepInfra가 기본 provider로 합류했다

DeepInfra가 bundled provider로 추가된 것도 큰 변화입니다. 단순히 텍스트 모델 하나가 늘어난 정도가 아니라, 모델 discovery, 이미지 생성과 편집, 이미지·오디오 이해, TTS, text-to-video, 메모리 임베딩까지 폭넓게 연결됩니다.

OpenClaw를 여러 provider 중심으로 운영하는 입장에서는 선택지가 하나 더 생긴다는 의미가 큽니다. 특히 미디어 생성과 임베딩까지 같이 묶여 있기 때문에, 비용·속도·품질을 비교하면서 워크플로를 설계하기가 더 좋아졌습니다.

## 채널 지원: Yuanbao와 QQBot 확장

중국권 채널 지원도 강화됐습니다. Tencent Yuanbao는 공식 채널 카탈로그와 문서에 등록됐고, QQBot은 그룹 채팅, 멘션 기반 활성화, 스트리밍 메시지, 대용량 미디어 업로드, 파이프라인 구조 개선이 포함됐습니다.

이런 변화는 단순한 채널 추가보다 의미가 있습니다. OpenClaw가 특정 메신저 한두 개에 묶인 도구가 아니라, 다양한 채널에서 같은 에이전트 운영 방식을 확장하려는 방향으로 가고 있다는 신호로 볼 수 있습니다.

## 플러그인과 모델 카탈로그는 manifest-first 방향으로 이동

이번 릴리스에는 플러그인 SDK와 모델 카탈로그 관련 변경이 많습니다. 핵심은 manifest-first입니다. provider catalog, alias, suppression, startup activation 같은 정보를 런타임 코드에 흩어두기보다 플러그인 manifest에 더 명확히 선언하는 방향입니다.

겉으로는 개발자용 내부 정리처럼 보일 수 있지만, 운영자 입장에서도 중요합니다. Gateway 시작 시 불필요한 플러그인 로딩을 줄이고, 모델 목록이나 provider alias가 어디서 왔는지 추적하기 쉬워지기 때문입니다. 이런 구조 정리는 시간이 지날수록 안정성 차이로 나타납니다.

## 안정성 수정: Telegram, Slack, Gateway가 더 단단해졌다

수정 항목은 매우 많지만, 운영자가 체감할 만한 부분만 추리면 이렇습니다.

- Telegram 시작과 전송 경로의 타임아웃, Bot API fallback, 잘못된 apiRoot 처리 개선
- Slack Socket Mode의 ping/pong 타임아웃과 media download stall 방지
- Gateway 시작 시 primary model prewarm이 채널 시작을 막지 않도록 조정
- 세션 thinking default와 Control UI 표시 정합성 개선
- cron의 Telegram topic/thread 전달 보존 개선
- 민감 토큰이 콘솔 로그로 새는 경로까지 redaction 적용
- 플러그인 runtime deps 캐시와 mirror 처리 개선으로 재시작·업데이트 안정성 강화

특히 Telegram과 Slack은 실제 봇 운영에서 자주 쓰이는 채널이라, 이런 “멈춤 방지” 계열 수정이 꽤 중요합니다. 기능이 늘어나는 것보다, 메시지가 제때 오고 가는 게 운영에서는 더 먼저입니다.

## 정리

OpenClaw 2026.4.27은 기능 확장과 운영 안정화가 같이 들어간 릴리스입니다. Codex Computer Use, DeepInfra, Yuanbao/QQBot 같은 확장은 앞으로 할 수 있는 일을 넓히고, Telegram·Slack·Gateway·플러그인·세션 관련 수정은 매일 쓰는 환경을 덜 불안하게 만듭니다.

제 기준에서 이번 업데이트의 방향은 명확합니다. OpenClaw가 단순한 AI 채팅 도구가 아니라, 여러 provider와 채널, 플러그인을 오래 운영하는 시스템으로 더 다듬어지고 있습니다.

원문 : <a href="https://github.com/openclaw/openclaw/releases/tag/v2026.4.27">OpenClaw 2026.4.27 Release Notes</a>
