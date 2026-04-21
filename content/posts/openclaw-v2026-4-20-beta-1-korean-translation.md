---
title: "OpenClaw 2026.4.20-beta.1 정리, 이번엔 기능보다 운영 안정화가 핵심이다"
date: 2026-04-21T23:41:00+09:00
draft: false
description: "OpenClaw v2026.4.20-beta.1 릴리즈 노트를 한국어로 번역하고 핵심 변경점을 정리했습니다. 이번 업데이트는 기능 추가보다 세션, Cron, Telegram, Gateway, 보안 등 운영 안정화에 더 무게를 둡니다."
tags:
  - OpenClaw
  - 릴리즈노트
  - 번역
  - AI 에이전트
  - Gateway
  - Cron
  - Telegram
  - Moonshot Kimi
categories:
  - OpenClaw
  - 번역
---

# OpenClaw 2026.4.20-beta.1 정리, 이번엔 기능보다 운영 안정화가 핵심이다

원문: https://github.com/openclaw/openclaw/releases/tag/v2026.4.20-beta.1  
문서 유형: OpenClaw 릴리즈 노트 번역 및 해설  
#OpenClaw #릴리즈노트 #번역 #AI에이전트 #Gateway #Cron #Telegram #MoonshotKimi

## 먼저 핵심만 보면

- 기본 시스템 프롬프트와 GPT-5 오버레이가 더 강해졌다
- 세션 유지보수와 스토어 prune이 기본값에서 더 강화됐다
- Moonshot/Kimi 기본 정책과 thinking 처리 방식이 더 명확해졌다
- Cron, Telegram, Gateway, Pairing 주변 운영 이슈가 많이 정리됐다
- OpenAI Codex, Anthropic, Copilot 같은 다중 provider 호환성도 손봤다
- 보안 가드와 런타임 보호 장치가 여러 군데서 강화됐다

이번 OpenClaw 릴리즈는 화려한 기능 추가보다 더 중요하다.  
실제 운영에서 사람을 지치게 하던 문제들을 꽤 많이 건드렸기 때문이다.  
세션, Cron, Telegram, Gateway, Pairing, 그리고 보안까지, 전체적으로 **“덜 불안한 OpenClaw”**에 가까워졌다.

즉, 이번 버전은 단순히 기능이 늘어난 릴리즈가 아니다.  
**실제로 오래 켜두고 굴릴 때 더 안정적으로 버티게 만드는 운영형 업데이트**에 가깝다.

---

## 왜 이번 릴리즈가 중요한가

OpenClaw 같은 에이전트 시스템은 데모보다 운영이 훨씬 어렵다.  
처음 며칠은 잘 돌아가도, 시간이 지나면 세션이 쌓이고, Cron이 늘어나고, Telegram polling이 흔들리고, pairing이나 auth 같은 자잘한 문제가 사람을 더 피곤하게 만든다.

이번 `v2026.4.20-beta.1`은 바로 그 지점을 많이 건드린 릴리즈다.

그래서 이번 업데이트는 이런 팀에게 특히 체감이 클 가능성이 높다.

- 프롬프트와 시스템 프롬프트 품질에 민감한 팀
- 세션이 오래 쌓이며 메모리나 스토어 부하가 걱정되던 팀
- Cron, Telegram, Gateway, Pairing 쪽에서 운영 이슈를 겪던 팀
- Moonshot/Kimi, OpenAI Codex, Anthropic, Copilot 같은 다중 provider 구성을 쓰는 팀

한 줄로 요약하면 이렇다.

> 이번 릴리즈는 OpenClaw를 더 화려하게 만들기보다, 더 오래 안정적으로 굴리기 위한 패치에 가깝다.

---

## 1. 프롬프트와 에이전트 기본 동작이 더 강해졌다

릴리즈 노트에서 가장 먼저 보이는 변화 중 하나가 이 부분이다.

- 기본 system prompt 강화
- OpenAI GPT-5 overlay 강화
- completion bias 명확화
- live-state checks 추가
- weak-result recovery 강화
- final 전 verification guidance 강화

이게 왜 중요하냐면, 에이전트 품질은 모델 자체만으로 결정되지 않기 때문이다.  
실제로는 **어떤 시스템 프롬프트와 운영 규칙 위에서 모델을 굴리느냐**가 결과를 크게 바꾼다.

이번 변경은 특히 다음 문제를 줄이려는 의도가 보인다.

- 적당히 끝내버리는 성향
- 현재 상태를 충분히 확인하지 않고 답하는 문제
- 약한 중간 결과를 그냥 넘겨버리는 문제
- 검증 없이 최종 답을 내는 흐름

즉, OpenClaw가 기본적으로 더 **완료 지향적이고, 검증 지향적인 에이전트 행동**을 하도록 조정됐다고 볼 수 있다.

운영자는 보통 여기서 체감한다.  
같은 모델을 써도, 기본 프롬프트가 얼마나 잘 설계돼 있느냐에 따라 결과의 안정감이 크게 달라지기 때문이다.

---

## 2. 세션 스토어가 너무 커져서 터지는 문제를 더 세게 막는다

운영하는 입장에서는 이 변화가 꽤 반갑다.

릴리즈 노트에 따르면 이제:

- built-in entry cap 기본 적용
- age prune 기본 적용
- oversized store를 load 시점에서 prune

이 조합이 들어간다.

왜 중요하냐면, Cron이나 executor 세션이 오래 쌓이면 스토어가 너무 커져서  
**쓰기 전에 이미 Gateway가 메모리 문제를 일으키는 상황**이 생길 수 있기 때문이다.

이번 변경은 그 문제를 꽤 현실적으로 다룬다.  
즉, 문제가 write path까지 가기 전에 **load 단계에서 미리 정리**하는 방식이다.

한마디로 말하면,

> “세션이 쌓여서 언젠가 한 번 크게 터지는” 구조를 기본값에서 더 강하게 막기 시작했다.

이건 데모보다 실전에서 훨씬 중요한 변화다.  
운영 시스템은 한 번 멋지게 작동하는 것보다, 오래 쌓여도 안 터지는 쪽이 훨씬 값지기 때문이다.

---

## 3. Moonshot/Kimi 기본값도 바뀌었다

이번 릴리즈에서는 Moonshot/Kimi 관련 변경도 꽤 눈에 띈다.

주요 내용은 이렇다.

- 번들 기본 Moonshot setup, web search, media-understanding surface를 `kimi-k2.6`으로 이동
- `kimi-k2.5`는 호환성용으로 유지
- `moonshot/kimi-k2.6`에서 `thinking.keep = "all"` 허용
- 다른 Moonshot 모델이나 pinned `tool_choice`가 thinking을 막는 경우에는 해당 설정 제거
- 기본 bundled Kimi thinking은 off로 정리

이 변화는 결국 **기본 모델 정책을 더 명확하게 정리하는 작업**으로 읽힌다.

예전에는 세션 상태나 모델 조합 때문에 thinking이 애매하게 남아 있거나,  
의도치 않게 reasoning이 다시 켜지는 상황이 있을 수 있었다.

이번 업데이트는 그런 부분을 줄이고,

- 어떤 모델이 기본인지
- 어떤 thinking 모드가 허용되는지
- 언제 thinking payload를 제거해야 하는지

를 더 명확히 정리한 쪽이다.

여기서 중요한 건 단순히 기본 모델 이름이 바뀌었다는 점이 아니다.  
**운영자가 예상 가능한 방식으로 모델이 움직이도록 정리했다**는 점이 더 중요하다.

---

## 4. Cron은 이제 운영용 파일과 상태 파일이 더 분리된다

이번 릴리즈에서 꽤 실무적인 변화 중 하나가 이거다.

- runtime execution state를 `jobs-state.json`으로 분리
- `jobs.json`은 git-tracked job definition 용도로 안정적으로 유지

이건 사소해 보이지만 매우 실용적이다.

Cron job 정의 파일을 git으로 관리하고 싶은 사람 입장에서는,  
실행 상태까지 같은 파일에 섞이면 diff가 지저분해지고 리뷰도 어려워진다.

이번 변경으로 이제:

- `jobs.json`은 선언적 설정 파일
- `jobs-state.json`은 런타임 상태 파일

역할이 더 분명해진다.

이건 운영하는 사람 입장에서 아주 반가운 정리다.

작아 보이지만, 이런 분리는 나중에 관리 비용을 크게 줄인다.  
설정 파일은 설정 파일답게, 상태 파일은 상태 파일답게 남아 있어야 팀 작업도 쉬워진다.

---

## 5. Telegram과 Cron delivery 주변이 꽤 많이 다듬어졌다

이번 릴리즈는 Telegram 운영 안정성과 Cron delivery 쪽 수정이 특히 많다.

예를 들면:

- Telegram polling watchdog 기본 임계값을 90초에서 120초로 상향
- `channels.telegram.pollingStallThresholdMs` 설정 가능
- persisted-offset confirmation `getUpdates` probe에 client timeout 추가
- explicit `delivery.mode: "none"` 처리 정교화
- recurring Telegram announce dedupe 문제 수정
- `heartbeat.target="last"` 보존 개선
- isolated-agent delivery 라우팅 정리

이런 수정들은 전부 눈에 띄는 새 기능은 아니다.  
근데 실제 운영에서는 이런 자잘한 문제들이 훨씬 더 스트레스를 준다.

즉, 이번 릴리즈는 Telegram과 Cron을 **“더 똑똑하게” 만든다기보다 “덜 말썽 부리게” 만든다**는 느낌이 강하다.

운영자는 바로 이런 곳에서 체감한다.  
유저는 가끔 한 번 실패한 메시지만 보지만, 운영자는 그 뒤에서 반복적으로 쌓이는 예외와 복구 비용을 계속 감당해야 하기 때문이다.

---

## 6. Gateway, Pairing, Status도 운영 친화적으로 바뀌었다

Gateway와 pairing 쪽도 꽤 많은 수정이 들어갔다.

대표적으로:

- loopback shared-secret node-host, TUI, gateway clients를 local로 처리
- pairing required 실패에 더 구체적인 reason과 remediation hint 제공
- pending pairing request, scope-upgrade drift를 `openclaw doctor --fix`가 더 잘 설명
- status에서 reachability, capability, read-probe 보고를 분리
- websocket broadcast를 더 강하게 scope-gate
- paired-device session의 권한 범위 제한 강화

이건 결국 **“왜 안 되지?”를 조금 더 잘 설명해주는 방향**으로 보인다.

예전에는 pairing/auth/status 문제가 나면 사용자가 그냥 막막한 경우가 많았다.  
이번엔 적어도 원인 분리와 에러 메시지 품질이 좋아지는 쪽으로 움직였다.

이건 초보 사용자보다 오히려 운영자에게 더 큰 가치가 있다.

이런 개선은 데모에서는 티가 잘 안 난다.  
하지만 실제 환경에서는 문제를 빨리 이해하고 바로 복구할 수 있느냐가 운영 피로도를 크게 갈라놓는다.

---

## 7. 보안 패치도 꽤 많다

이번 릴리즈는 보안 관련 수정도 적지 않다.

눈에 띄는 부분만 추리면:

- qqbot direct-upload URL 경로 SSRF guard
- template-rendered mapping sessionKeys 보호 강화
- `NODE_OPTIONS` 같은 interpreter-startup env key 차단
- workspace `.env`에서 모든 `OPENCLAW_*` 키 차단
- `MINIMAX_API_HOST` workspace env injection 차단
- gateway tool의 `config.patch`, `config.apply` 가 operator-trusted path를 못 건드리게 강화
- websocket broadcast를 권한별로 제한
- paired device가 다른 device pairing 요청을 못 건드리게 제한

이런 변경은 전부 “새 기능”처럼 보이진 않지만, 운영 플랫폼에서는 정말 중요하다.  
특히 OpenClaw처럼 plugin, gateway, MCP, multi-provider, device pairing이 섞인 시스템은  
작은 권한 구멍이 전체 운영 리스크로 이어질 수 있다.

이번 릴리즈는 그런 면에서 **보안 표면을 꽤 성실하게 줄이고 있다**는 인상을 준다.

보안은 잘될 때는 티가 안 나지만, 한 번 뚫리면 모든 기능 개선이 무의미해진다.  
그래서 이런 종류의 수정은 눈에 띄지 않아도 높은 점수를 줄 만하다.

---

## 8. OpenAI Codex, Anthropic, Copilot 호환성도 챙겼다

모델/provider 쪽 수정도 실무적으로 중요하다.

예를 들면:

- OpenAI Codex의 legacy `openai-completions` override를 native Codex Responses transport로 정리
- ChatGPT/Codex OAuth Responses 요청을 `/backend-api/codex`로 라우팅
- Anthropic `api: "anthropic-messages"` 기본값을 Anthropic-owned provider에만 적용
- GitHub Copilot onboarding 기본 모델을 `claude-opus-4.6`으로 정리
- GPT reasoning model에서 `/think off` 처리 개선
- 모델별 supported reasoning effort에 맞게 `/think` 매핑 정리

이런 부분은 멀티 provider 환경을 쓰는 팀에 특히 중요하다.  
표면적으로는 작은 transport 수정 같아 보여도, 실제론 **잘 되던 세션이 갑자기 깨지는 문제**와 직결되기 때문이다.

여기는 기능보다 호환성 유지가 더 중요하다.  
운영자는 새 기능보다 “어제 되던 게 오늘도 되는가”에 훨씬 민감하기 때문이다.

---

## 9. 자잘하지만 중요한 운영 품질 개선도 많다

릴리즈 노트를 끝까지 보면, 체감은 작아도 실제 운영에는 꽤 중요한 수정들이 많다.

예를 들면:

- plugin runtime dependency 설치/복구 경로 개선
- repeated gateway start 시 로그 조용하게 정리
- plugin duplicate id precedence 정리
- Active Memory recall 실패 시 전체 turn 실패 대신 graceful degrade
- browser profile routing 개선
- BlueBubbles send timeout 상향과 reaction fallback 개선
- Matrix allowlist hot reload
- slash command 인식 안정화
- Mattermost draft preview 개선
- `sanitizeForLog()` 최적화

이런 수정들은 다 모이면 꽤 크다.  
왜냐면 OpenClaw는 “큰 기능 하나”보다 **많은 작은 부품이 동시에 잘 맞물려야 하는 시스템**이기 때문이다.

결국 운영 품질은 이런 작은 개선들의 합으로 올라간다.  
한 줄짜리 패치가 모여서, 나중에는 “왠지 예전보다 덜 피곤한 시스템”을 만든다.

---

## 한국어 번역으로 짧게 정리하면

이번 `v2026.4.20-beta.1` 릴리즈는 다음 흐름으로 이해하면 된다.

- 기본 프롬프트와 모델 오버레이를 더 강하게 다듬었고
- 세션과 스토어 유지보수를 강화했고
- Moonshot/Kimi, Codex, Anthropic, Copilot 호환성을 손봤고
- Cron, Telegram, Gateway, Pairing의 운영 이슈를 많이 줄였고
- 보안 가드를 여러 군데서 강화했다

즉, **새로운 장난감을 추가한 릴리즈라기보다, 실제로 굴리는 OpenClaw를 덜 불안하게 만드는 릴리즈**다.

---

## 마무리

이번 릴리즈는 OpenClaw를 더 멋지게 보이게 만드는 버전이 아니다.  
대신 실제로 오래 켜두고 굴릴 때 덜 불안하게 만드는 버전이다.  
운영해 본 사람일수록, 이번 업데이트를 더 높게 볼 가능성이 크다.

특히 이런 사람이라면 더 반길 만하다.

- Gateway를 오래 켜두는 사람
- Cron과 Telegram 자동화를 많이 쓰는 사람
- 여러 provider를 섞어 쓰는 사람
- pairing, auth, delivery 문제로 삽질했던 사람

한 줄 결론은 이거다.

> OpenClaw 2026.4.20-beta.1은 새 기능 과시용 릴리즈가 아니라, 실제 운영을 덜 피곤하게 만드는 릴리즈다.
