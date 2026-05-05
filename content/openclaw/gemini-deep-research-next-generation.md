---
title: "Gemini Deep Research Max: 자율 리서치 에이전트의 새 시대"
date: 2026-05-05T15:35:00+09:00
draft: false
description: "Google DeepMind가 Gemini 3.1 Pro 기반의 두 가지 자율 리서치 에이전트를 공개했다. MCP 지원, 네이티브 시각화, 멀티모달 입력 등 기업급 분석을 가능하게 하는 Deep Research와 Deep Research Max의 핵심 기능을 자세히 살펴본다."
tags:
  - Gemini
  - DeepResearch
  - GoogleAI
  - AI에이전트
  - MCP
  - 자율에이전트
  - LLM
  - GeminiAPI
  - 리서치자동화
categories:
  - AI 에이전트
  - Google AI
aliases:
  - /posts/gemini-deep-research-next-generation/
cover:
  image: /images/gemini-deep-research/gemini-3.1-pro_deep-research-and-max_blog_evals_doc.png
  alt: Deep Research Max 벤치마크 평가 결과 차트
  relative: false
---

# Gemini Deep Research Max: 자율 리서치 에이전트의 새 시대

Google DeepMind가 2026년 4월 21일, **Gemini 3.1 Pro** 기반의 차세대 자율 리서치 에이전트 두 가지를 공개했다. 표준 **Deep Research**와 한 단계 위의 **Deep Research Max**다. 금융, 생명과학, 시장조사 등 전문 분야에서 기업급 분석을 자동화하는 게 목표다.

작년 12월 Gemini API의 Interactions API를 통해 개발자 미리보기로 선보인 이후, 이번 업데이트는 단순한 성능 향상이 아니라 **에이전트의 역할 자체를 재정의**한다.

## 두 가지 에이전트, 서로 다른 목적

### Deep Research (Standard)

빠른 응답이 필요한 인터랙티브 서비스에 최적화됐다. 12월 미리보기를 완전히 대체하는 버전으로, **지연 시간을 크게 줄이면서도 품질은 오히려 높아졌다**. 사용자가 직접 결과를 기다리는 UI에 붙이기에 적합하다.

### Deep Research Max

**최대 분석 깊이**를 추구하는 버전이다. 확장된 테스트 타임 컴퓨트(extended test-time compute)를 활용해 반복적인 추론, 검색, 보고서 정제를 거친다. 비동기 백그라운드 워크플로우에 최적—예를 들어 밤새 실행되는 크론 작업으로 심층 실사(due diligence) 보고서를 자동 생성하는 시나리오에 딱 맞는다.

## 성능 벤치마크: 얼마나 나아졌나

![Deep Research Max 벤치마크 결과](/images/gemini-deep-research/gemini-3.1-pro_deep-research-and-max_blog_evals_doc.png)

내부 전문가 평가에서 **Deep Research 4/26 대 12/25**를 비교했을 때, 새 버전은 훨씬 더 많은 소스를 검토하고, 이전에는 놓쳤던 중요한 뉘앙스를 포착하는 것으로 나타났다. SEC 공시, 동료심사 저널 같은 권위 있는 1차 자료를 광범위하게 활용하며, 상충하는 증거를 체계적으로 저울질해 **실행 가능한 전문가급 분석**을 만들어낸다.

## 핵심 신기능

### 1. MCP(Model Context Protocol) 지원

가장 큰 변화 중 하나다. 이제 Deep Research는 웹 검색에만 의존하지 않는다. **MCP를 통해 기업 내부 데이터베이스, 금융 데이터 제공업체, 전문 데이터 저장소에 안전하게 접속**할 수 있다.

파트너십도 함께 발표됐다:
- **FactSet**: 금융 데이터 통합
- **S&P Global**: 신용평가·시장 인텔리전스
- **PitchBook**: 투자 리서치 데이터

이 세 곳은 각각 MCP 서버를 구축해 Deep Research 워크플로우에 자사 데이터를 직접 제공한다. 에이전트가 단순한 웹 검색 도구에서 **엔터프라이즈 데이터 플랫폼**으로 진화하는 핵심 고리다.

### 2. 네이티브 차트·인포그래픽

Gemini API 최초로 **보고서 안에 고품질 차트와 인포그래픽을 직접 생성**하는 기능이 추가됐다. HTML 또는 Nano Banana 형식으로 복잡한 데이터셋을 시각화해 프레젠테이션 바로 쓸 수 있는 수준의 결과물을 만든다.

아래는 실제로 생성된 시각화 예시들이다:

![통화 성과 비교: 달러 대비 YoY 퍼포먼스 (2025.4~2026.4)](/images/gemini-deep-research/visual_1.png)

*어떤 통화가 달러 대비 강세·약세였는지 한눈에 보여주는 차트.*

![FIG 레짐의 4년 사이클](/images/gemini-deep-research/visual_2.png)

*금융 제도(FIG) 사이클을 분석한 복합 차트.*

![유럽 핀테크 자본 배분: 결제 인프라 우위](/images/gemini-deep-research/visual_3.png)

*유럽 핀테크 투자 흐름을 인포그래픽으로 정리.*

![글로벌 에너지 무역 재편: 주요 해상 우회로 (2024~2026)](/images/gemini-deep-research/visual_4.png)

*지정학적 변화로 바뀐 글로벌 에너지 해상 루트 지도.*

### 3. 협업적 리서치 플래닝

에이전트가 리서치 계획을 먼저 생성하면, 사용자가 이를 검토하고 **방향을 조정한 뒤 실행**할 수 있다. 조사 범위를 세밀하게 통제할 수 있어, 원하는 결과물에 더 가깝게 이끌어 갈 수 있다.

### 4. 확장된 툴링

동시에 다음 도구들을 함께 활용한다:
- **Google Search**: 최신 웹 정보 수집
- **원격 MCP 서버**: 전문 데이터소스 연결
- **URL Context**: 특정 페이지 내용 추출
- **코드 실행**: 데이터 분석·계산
- **파일 검색**: 업로드된 문서 탐색

웹 접근을 비활성화하고 기업 내부 데이터만 검색하도록 설정하는 것도 가능하다.

### 5. 멀티모달 리서치 그라운딩

PDF, CSV, 이미지, 오디오, 비디오를 입력으로 받아 에이전트 리서치의 맥락(context)으로 활용한다. 기존 보고서나 내부 자료를 기반으로 더 깊은 분석을 진행할 수 있다.

### 6. 실시간 스트리밍

중간 추론 단계를 실시간 사고 요약(live thought summaries)으로 확인하고, 텍스트와 이미지 출력을 생성되는 즉시 받을 수 있다. 인터랙티브 UI에서 특히 유용하다.

## 기존 제품과의 연동

Deep Research 인프라는 이미 Google 제품군에 통합되어 있다:

- **Gemini App** (전용 Deep Research 섹션)
- **NotebookLM**
- **Google Search** (AI 모드)
- **Google Finance**

이번 API 공개로 서드파티 개발자들도 같은 수준의 리서치 엔진을 자체 서비스에 내장할 수 있게 됐다.

## 접근 방법

두 에이전트 모두 2026년 4월 21일부터 **Gemini API 유료 티어 퍼블릭 프리뷰**로 제공된다. Interactions API를 통해 접근하며, Google Cloud를 통한 스타트업·엔터프라이즈 버전도 곧 출시 예정이다.

개발자 문서는 [ai.google.dev/gemini-api/docs/deep-research](https://ai.google.dev/gemini-api/docs/deep-research)에서 확인할 수 있다.

---

## 정리

Deep Research Max가 흥미로운 이유는 단순히 "더 빠른 요약"이 아니라는 점이다. MCP로 기업 내부 데이터와 연결되고, 차트를 직접 만들고, PDF와 비디오를 입력으로 받아 분석하는 전 과정이 하나의 에이전트 안에서 이뤄진다.

금융 실사, 경쟁사 분석, 시장 리서치처럼 **시간과 전문성이 많이 드는 반복 작업**에서 AI 에이전트의 실용적 가치가 본격적으로 드러나기 시작했다. Gemini 3.1 Pro 기반의 이 두 에이전트는 그 전환점을 잘 보여주는 사례다.

---

*원문: [Deep Research Max: a step change for autonomous research agents](https://blog.google/innovation-and-ai/models-and-research/gemini-models/next-generation-gemini-deep-research/) — Google DeepMind, Lukas Haas & Srinivas Tadepalli (2026.04.21)*
