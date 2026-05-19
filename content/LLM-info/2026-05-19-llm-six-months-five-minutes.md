---
title: "지난 6개월 LLM 변화, 5분 안에 봐야 하는 이유"
date: 2026-05-19T19:45:00+09:00
draft: false
description: "Simon Willison의 PyCon US 2026 라이트닝 토크를 바탕으로, 최근 6개월 LLM 생태계의 핵심 변화인 모델 경쟁, coding agent의 성장, local LLM의 약진을 정리한다."
tags:
  - LLM
  - AI
  - CodingAgents
  - LocalLLM
  - SimonWillison
  - PyCon
categories:
  - LLM 소식
  - AI
aliases:
  - /posts/2026-05-19-llm-six-months-five-minutes/
cover:
  image: "/images/llm-six-months-handdrawn-topology-cover.png"
  alt: "Hand-drawn topology diagram about six months of LLM progress, coding agents, local models, and developer tools"
  caption: "Hand-drawn topology style illustration"
---

추천태그: #LLM #AI에이전트 #CodingAgents #LocalLLM #SimonWillison

**핵심내용 요약:**
- Simon Willison은 PyCon US 2026 라이트닝 토크에서 최근 6개월 LLM 변화를 5분 발표로 정리했다.
- 핵심 흐름은 최고 모델 경쟁의 빠른 교체, coding agent의 급성장, local LLM의 기대 이상 성능이다.
- LLM 시장은 이제 “누가 가장 큰 모델을 만들었나”보다 “실제 작업을 얼마나 잘 수행하나”로 이동하고 있다.

---

## 기: 6개월 만에 LLM 판이 또 바뀌었다

LLM 세계는 반년만 지나도 완전히 다른 풍경이 된다. Simon Willison은 PyCon US 2026 라이트닝 토크에서 **지난 6개월의 LLM 변화**를 5분짜리 annotated slides로 압축했다.

짧은 발표지만, 그 안에는 지금 AI 생태계의 방향을 읽을 수 있는 중요한 단서가 들어 있다.

## 승: 최고 모델은 계속 바뀌고, agent는 강해졌다

Willison이 짚은 첫 번째 변화는 **최고 모델의 왕좌가 빠르게 바뀌었다**는 점이다. Anthropic, OpenAI, Google 사이에서 “best model”의 위치가 여러 번 이동했다.

두 번째 변화는 coding agent의 성장이다. 단순히 코드를 제안하는 수준을 넘어, GitHub commit을 만들고 프로젝트 구조를 이해하며 실제 개발 흐름에 들어오기 시작했다. Reinforcement Learning from Verifiable Rewards 같은 접근이 이 흐름을 더 밀어 올렸다.

## 전: local LLM이 기대를 넘어섰다

흥미로운 지점은 local LLM이다. Willison은 Qwen3.6-35B-A3B 같은 모델이 노트북에서 돌면서도 예상보다 강한 결과를 냈다고 소개한다. Gemma 4, GLM-5.1 등 다양한 모델도 예시로 등장한다.

즉, AI 경쟁은 거대 클라우드 모델만의 이야기가 아니다. 점점 더 많은 실험이 개인 장비와 오픈 모델 위에서 가능해지고 있다.

## 결: 다음 6개월의 관전 포인트

이번 정리의 핵심은 명확하다. 앞으로 LLM 경쟁은 모델 이름보다 **실제 사용성**에서 갈릴 가능성이 크다.

coding agent가 얼마나 안정적으로 일을 끝내는지, local model이 얼마나 실용적인 수준까지 올라오는지, 그리고 개발자가 이 도구들을 어떤 워크플로우에 붙일 수 있는지가 중요해진다.

지난 6개월이 빠르게 변했다면, 다음 6개월은 더 빠를 가능성이 높다.

---

원문 출처: [The last six months in LLMs in five minutes](https://simonwillison.net/2026/May/19/5-minute-llms/)