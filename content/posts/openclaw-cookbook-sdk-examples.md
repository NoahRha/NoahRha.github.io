---
title: "OpenClaw Cookbook: SDK 예제로 에이전트 앱을 빠르게 시작하는 방법"
date: 2026-05-01T11:55:00+09:00
draft: false
description: "openclaw/cookbook 저장소를 바탕으로 OpenClaw SDK 예제 구조, recipes와 starter apps, Gateway 연결 방식, 실무 활용 포인트를 한국어로 정리했다."
tags:
  - OpenClaw
  - OpenClawSDK
  - Cookbook
  - AI에이전트
  - TypeScript
  - 개발자도구
categories:
  - OpenClaw
  - AI 에이전트
---

# OpenClaw Cookbook: 에이전트 앱을 만들기 위한 실전 예제 모음

OpenClaw Cookbook은 OpenClaw SDK로 앱, 도구, 자동화를 만들 때 참고할 수 있는 실행 가능한 예제 저장소입니다. 문서만 읽고 감을 잡는 방식이 아니라, 바로 복사해서 돌려볼 수 있는 TypeScript 예제를 중심으로 구성되어 있습니다.

이 저장소의 핵심은 단순합니다. OpenClaw를 “채팅으로 쓰는 도구”에서 한 단계 더 나아가, 직접 만든 앱이나 운영 화면, CLI, 테스트 환경 안에 넣고 싶은 개발자를 위한 출발점입니다.

## 구조는 recipes와 sdk 두 층으로 나뉜다

Cookbook은 크게 두 영역으로 구성됩니다.

첫 번째는 `recipes/`입니다. 여기는 하나의 개념만 보여주는 작은 예제들이 들어갑니다. 에이전트 실행, 이벤트 스트리밍, 실행 취소, 세션 재사용, 모델 상태 확인, 커스텀 transport 테스트처럼 SDK를 쓰다 보면 꼭 필요한 기본 동작을 작게 쪼개서 보여줍니다.

두 번째는 `sdk/`입니다. 여기는 실제 제품의 출발점에 가까운 standalone starter app이 들어갑니다. CLI 앱, React 기반 workbench, 운영 대시보드처럼 “이걸 복사해서 내 프로젝트에 붙일 수 있겠다” 싶은 예제들입니다.

## 바로 시작하는 흐름

저장소를 받아서 전체 검사를 돌리는 기본 흐름은 간단합니다.

```bash
pnpm install
pnpm check
```

가장 작은 로컬 예제는 `custom-transport`입니다.

```bash
pnpm recipe:custom-transport -- "test prompt"
```

이 예제는 in-memory transport를 사용하기 때문에 Gateway가 떠 있지 않아도 실행할 수 있습니다. SDK 코드를 테스트하거나 앱 로직을 분리해서 검증할 때 유용한 구조입니다.

## Gateway와 연결하는 예제

실제 OpenClaw와 연결하려면 Gateway URL 또는 local discovery를 사용합니다.

```bash
pnpm add @openclaw/sdk
export OPENCLAW_GATEWAY=auto
export OPENCLAW_AGENT_ID=main
pnpm recipe:run-agent -- "Summarize this repository"
```

보호된 Gateway라면 token이나 password를 환경변수로 넘깁니다.

```bash
export OPENCLAW_GATEWAY=ws://127.0.0.1:1455
export OPENCLAW_TOKEN=...
```

여기서 중요한 점은 예제 코드가 `@openclaw/sdk`를 직접 import하도록 맞춰져 있다는 것입니다. 현재는 SDK 패키지가 OpenClaw 본 저장소에 먼저 들어가는 단계라 cookbook 내부에서는 private workspace shim을 사용하지만, 나중에 실제 SDK가 배포되면 코드 모양을 크게 바꾸지 않고 옮겨갈 수 있습니다.

## 어떤 예제부터 보면 좋을까

가장 기본적인 요청·응답 흐름을 보고 싶다면 `recipes/run-an-agent`부터 보면 됩니다. 하나의 prompt를 보내고 안정적인 결과 envelope를 받는 최소 흐름입니다.

실시간 UI를 만들고 싶다면 `recipes/stream-events`가 중요합니다. 에이전트가 작업하는 중간 이벤트를 받아 화면에 표시하려면 normalized event iteration 구조가 필요합니다.

중지 버튼이나 시간 제한이 필요하다면 `recipes/cancel-a-run`을 보면 됩니다. 실행 중인 run id를 기준으로 취소하는 흐름을 다룹니다.

대화형 앱을 만든다면 `recipes/reuse-session`이 핵심입니다. session key를 안정적으로 유지해야 여러 턴의 대화가 하나의 흐름으로 이어집니다.

모델과 인증 상태를 보여주는 운영 화면을 만들고 싶다면 `recipes/model-status`가 출발점입니다. provider readiness와 auth 상태를 확인하는 패턴을 볼 수 있습니다.

## starter app은 제품화 감각을 준다

`sdk/quickstart`는 가장 작은 완성형 run, stream, wait 흐름을 보여줍니다. OpenClaw SDK를 처음 붙이는 개발자가 전체 그림을 보기에 좋습니다.

`sdk/coding-agent-cli`는 터미널 기반 agent workflow를 다룹니다. 단발성 prompt뿐 아니라 interactive slash command까지 포함하므로, CLI 제품을 만들고 싶은 경우 참고할 만합니다.

`sdk/agent-workbench`는 React 기반 control room에 가깝습니다. prompt, model, session, event, cancel, result를 한 화면에서 다루는 구조라 내부 운영 도구나 실험용 UI를 만들 때 유용합니다.

`sdk/run-board`는 run 상태, model, session, activity 기준으로 작업을 묶어 보여주는 운영 대시보드 예제입니다. 여러 에이전트 실행을 관찰해야 하는 팀에게 좋은 시작점입니다.

## 실무자가 볼 포인트

OpenClaw Cookbook의 가치는 “SDK 기능 목록”이 아니라 **복사 가능한 작업 단위**에 있습니다. 에이전트 앱을 만들 때 막히는 지점은 대개 모델 호출 자체가 아니라, 실행 상태를 어떻게 보여줄지, 취소를 어떻게 처리할지, 세션을 어떻게 이어갈지, Gateway 없이 테스트를 어떻게 할지 같은 주변 구조입니다.

Cookbook은 그 주변 구조를 작게 분리해 보여줍니다. 그래서 처음부터 거대한 앱을 만들기보다, 필요한 recipe를 하나씩 가져와 내 제품 형태에 맞게 붙이는 방식이 좋습니다.

OpenClaw를 개인 자동화나 메신저 봇으로만 쓰고 있다면 이 저장소가 당장 필요 없을 수도 있습니다. 하지만 OpenClaw를 내 서비스, CLI, 대시보드, 내부 운영 도구에 넣고 싶다면 Cookbook은 가장 먼저 열어볼 만한 개발자용 출발점입니다.

원문 : <a href="https://github.com/openclaw/cookbook">openclaw/cookbook</a>
