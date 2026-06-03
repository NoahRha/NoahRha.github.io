---
title: "구글 ERA, 과학 코딩을 ‘발견의 엔진’으로 바꾸다"
date: 2026-06-03T09:30:00+09:00
draft: false
description: "Google Research가 Nature 논문과 함께 공개한 Empirical Research Assistance(ERA)를 정리했습니다. 과학 실험 코드를 AI가 탐색·작성·최적화하면서 Computational Discovery로 이어지는 흐름을 살펴봅니다."
tags:
  - "Google Research"
  - "ERA"
  - "Computational Discovery"
  - "Gemini for Science"
  - "AI 과학"
categories:
  - "AI"
  - "LLM"
slug: "era-computational-discovery-google-research"
cover:
  image: "/images/era-computational-discovery-cover.png"
  alt: "핸드드로잉 스타일로 실험 노트와 분기 탐색, 과학 데이터가 발견 노드로 모이는 장면"
  caption: "gpt-image-2로 생성한 핸드드로잉 스타일 ERA / Computational Discovery 대표 이미지"
---

AI가 과학자를 대신해 결론을 내리는 시대라기보다, 과학자가 반복해야 했던 코딩 실험을 더 빠르게 굴리는 도구가 먼저 현실이 되고 있습니다. Google Research가 공개한 **Empirical Research Assistance(ERA)** 는 그 지점을 꽤 선명하게 보여줍니다.

## 목차

- [핵심 요약](#핵심-요약)
- [ERA는 무엇을 하는 도구인가](#era는-무엇을-하는-도구인가)
- [Nature 논문이 보여준 성능의 의미](#nature-논문이-보여준-성능의-의미)
- [실제 과학 문제에 어떻게 쓰였나](#실제-과학-문제에-어떻게-쓰였나)
- [Computational Discovery로 이어지는 흐름](#computational-discovery로-이어지는-흐름)
- [실무자가 볼 핵심 포인트](#실무자가-볼-핵심-포인트)
- [원문 출처](#원문-출처)

## 핵심 요약

- Google Research는 Gemini 기반 과학 코딩 도구 **ERA** 를 Nature 논문과 함께 공개했습니다.
- ERA는 과학 문제와 성공 기준을 받으면 문헌 탐색, 코드 작성, 해법 조합, 결과 평가를 반복합니다.
- Google은 유전체학, 공중보건, 위성 이미지 분석, 신경과학 예측, 시계열 예측, 수학 벤치마크에서 전문가급 성능을 확인했다고 설명합니다.
- 최근 6개월 동안 ERA는 감염병 예측, 캘리포니아 유출수 예측, CO2 지도화, 3D 태양광 설계, 소매 예측 같은 실제 문제에 적용됐습니다.
- ERA와 AlphaEvolve는 Google Labs의 **Computational Discovery** 실험 도구로 이어지고 있습니다.

## ERA는 무엇을 하는 도구인가

ERA의 핵심은 “과학자가 실험 코드를 짜고 고치는 반복”을 AI가 도와주는 데 있습니다. 연구자가 문제와 평가 기준을 주면, ERA는 관련 문헌을 살피고 코드를 작성한 뒤 여러 해법을 탐색합니다. 단순히 코드 한 번 생성하고 끝나는 방식이 아니라, 결과를 평가하고 더 나은 방향으로 다시 조합하는 루프를 돕는 구조입니다.

Google은 ERA가 수천 개 선택지를 고려하며 tree search 방식으로 목표에 맞는 코드를 최적화한다고 설명합니다. 이 지점이 중요합니다. 과학 연구에서 병목은 아이디어 하나를 떠올리는 순간보다, 그 아이디어를 계산 가능한 실험으로 바꾸고 계속 다듬는 과정에 있는 경우가 많습니다. ERA는 바로 그 반복 구간을 겨냥합니다.

## Nature 논문이 보여준 성능의 의미

이번 글은 ERA를 다룬 Nature 논문 공개와 맞물려 나왔습니다. Google Research는 ERA를 유전체학, 공중보건, 위성 이미지 분석, 신경과학 예측, 일반 시계열 예측, 수학 문제 등 여러 벤치마크에서 테스트했고, 전문가급 성능을 냈다고 밝혔습니다.

여기서 볼 포인트는 “AI가 과학자를 대체한다”는 거친 주장보다, 전문 계산 모델링에 접근하는 문턱이 낮아질 수 있다는 점입니다. 특정 분야의 연구자가 고급 소프트웨어 엔지니어링 역량을 모두 갖추지 않아도, 더 정교한 계산 실험을 시도할 수 있게 되는 쪽에 가깝습니다. 이미 숙련된 연구자에게도 효과가 있습니다. 같은 시간 안에 더 많은 가설과 구현을 비교할 수 있기 때문입니다.

## 실제 과학 문제에 어떻게 쓰였나

Google은 최근 6개월 동안 연구자들과 ERA를 실제 문제에 적용했고, 총 8편의 원고가 나왔다고 소개합니다. 그중 새로 공개된 사례들은 꽤 넓은 영역을 덮습니다.

첫째, 공중보건 예측입니다. ERA는 미국 주 단위 병원 입원 수를 독감, 코로나19, RSV에 대해 최대 4주 앞서 예측하는 모델에 쓰였습니다. Google은 이 예측이 CDC 리더보드에서 세 호흡기 바이러스 모두 상위권 또는 최상위권에 올랐다고 설명합니다.

![ERA가 만든 호흡기 질환 병원 입원 예측 결과](/images/era-nature-forecasting.png)

둘째, 캘리포니아의 눈 녹은 물 기반 강 유출수 예측입니다. 이 모델은 주 공식 계절 물 공급 전망인 Bulletin 120보다 이른 봄철 유출수 예측에서 더 높은 정확도를 냈다고 합니다. 물 관리와 농업 의사결정에 직접 연결될 수 있는 사례입니다.

셋째, 대기 중 CO2 농도 지도화입니다. ERA가 만든 모델은 정지궤도 기상위성 데이터와 다른 정보를 결합해 10분 단위로 CO2 농도를 추정합니다. 도시 배출, 식물의 낮 시간 CO2 흡수, 자연·인간 활동 주기까지 더 촘촘하게 관찰하는 데 쓰일 수 있습니다.

![ERA가 위성 데이터로 추정한 남부 캘리포니아 CO2 농도 지도](/images/era-nature-co2-map.png)

그 밖에도 3D 태양광 에너지 극대화, Google Antigravity와 결합한 설계 탐색, 미국 경제 지표와 Google Trends를 활용한 소매 예측 사례가 소개됐습니다. 분야는 다르지만 공통점은 같습니다. ERA는 정답을 말하는 챗봇이 아니라, 실험 가능한 코드를 만들고 더 나은 계산 모델을 찾는 도구로 쓰였습니다.

## Computational Discovery로 이어지는 흐름

Google은 ERA와 AlphaEvolve를 바탕으로 **Computational Discovery** 라는 새 실험 도구를 Google Labs에서 trusted tester 프로그램으로 점진 공개한다고 밝혔습니다. Gemini for Science 안에는 Hypothesis Generation, Literature Insights 같은 실험도 함께 배치됩니다.

이 구성이 흥미로운 이유는 과학 방법론의 여러 단계를 나눠 지원하기 때문입니다. Literature Insights는 문헌을 이해하는 쪽, Hypothesis Generation은 가설을 만드는 쪽, Computational Discovery는 계산 실험과 발견을 밀어붙이는 쪽에 가깝습니다. 과학 AI가 하나의 만능 모델이 아니라, 연구 흐름의 단계별 도구 묶음으로 발전하고 있다는 신호로 볼 수 있습니다.

## 실무자가 볼 핵심 포인트

연구 조직이나 AI 제품 팀이 이번 발표에서 가져갈 포인트는 세 가지입니다.

1. 과학 AI의 경쟁력은 답변 문장보다 **반복 실험 루프**를 얼마나 잘 자동화하느냐에서 갈립니다.
2. 코드 생성은 시작일 뿐입니다. 평가 기준, 탐색 전략, 결과 비교, 재시도 루프가 함께 있어야 연구 도구가 됩니다.
3. 범용 AI를 과학에 붙일 때는 “전문가를 대체한다”보다 “전문가가 더 많은 후보를 더 빨리 검토하게 한다”는 관점이 현실적입니다.

ERA는 화려한 데모보다 실용적인 방향을 가리킵니다. 과학자가 매일 붙잡고 있는 계산 실험의 반복을 줄이고, 좋은 아이디어가 실제 코드와 결과로 이어지는 시간을 줄이는 것. 어쩌면 과학 AI의 첫 번째 큰 변화는 논문을 대신 쓰는 모델이 아니라, 실험을 더 빨리 굴리는 조용한 엔진에서 시작될 가능성이 큽니다.

## 원문 출처

*원문: [Empirical Research Assistance (ERA): From Nature publication to catalyzing Computational Discovery](https://research.google/blog/empirical-research-assistance-era-from-nature-publication-to-catalyzing-computational-discovery/) — Lizzie Dorfman, Michael Brenner, Google Research*
