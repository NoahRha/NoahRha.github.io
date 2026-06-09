---
title: "GEPA로 짓는 반사형 프롬프트 최적화: 다중 컴포넌트 + 구조화 피드백 + 홀드아웃 검증"
date: 2026-06-08T11:20:44+09:00
draft: false
description: "GEPA는 프롬프트를 한 덩어리가 아니라 지시/형식 컴포넌트로 쪼개 진화시키고, 점수와 자연어 피드백을 함께 던져 약한 모델을 반복적으로 끌어올린다. 12문항 학습·6문항 홀드아웃 검증으로 일반화까지 확인하는 구체 레시피."
tags: ["GEPA", "프롬프트최적화", "LLM", "에이전트", "평가"]
cover:
  image: /images/gepa-reflective-prompt-optimization/gepa-reflective-prompt-optimization-cover.png
  alt: "Reflective prompt optimization with GEPA"
  caption: "Generated illustration"
categories: ["LLM", "Agent"]
---

## 개요

수동 프롬프트 튜닝은 끝이 없다. 한 줄 고치고 돌려보고, 또 한 줄 고치고 다시 돌리고. MarkTechPost가 6월 7일 공개한 [GEPA 튜토리얼](https://www.marktechpost.com/2026/06/07/building-reflective-prompt-optimization-with-gepa-multi-component-prompts-structured-feedback-and-held-out-validation/)은 그 루프를 LLM 두 대와 점수 함수에 떠넘긴다. 약한 작업 모델은 풀고, 강한 리플렉션 모델은 프롬프트를 고친다. 사람은 평가 기준만 정확히 적어주면 된다.

## 핵심 요약

- 프롬프트를 `instructions`와 `format_rules` 두 컴포넌트로 분리해 함께 진화시킨다
- 점수 1.0 / 0.5 / 0.0과 자연어 피드백을 한 묶음으로 던져 리플렉션이 원인까지 짚게 한다
- 학습 12문항·홀드아웃 6문항으로 일반화 여부를 강제 검증한다
- 작업 모델은 `gpt-4o-mini`, 리플렉션 모델은 `gpt-4.1`, 호출 예산은 100회로 묶어 1~4분 안에 끝낸다
- 동시 4워커 병렬 평가로 후보 탐색 속도를 높이고, GitHub 코드 그대로 재현 가능하다

## GEPA가 풀려는 문제

기존 프롬프트 최적화는 한 줄짜리 시스템 프롬프트를 통째로 흔든다. 결과가 나빠도 어디가 문제인지 모른다. GEPA(Generic Evolutionary Prompt Adaptation)는 그 단일 덩어리를 **여러 컴포넌트의 사전**으로 본다. 튜토리얼의 시드 후보는 단 두 줄이다.

```python
seed_candidate = {
    "instructions": "Solve the math problem.",
    "format_rules": "Give the answer.",
}
```

리플렉션 모델은 이 두 필드를 따로따로 다듬는다. 추론 지시는 더 길고 단계적으로, 출력 규칙은 더 엄격하게. 결과는 한 줄짜리 프롬프트가 아니라, 역할이 분리된 작은 사양서가 된다.

## 점수만 주지 말고 이유까지 줘라

GEPA의 두 번째 핵심은 보상 구조다. 일반적인 강화학습용 보상은 0과 1이지만, 여기는 세 단계로 쪼갠다.

- **1.0**: 정답 + 형식 일치
- **0.5**: 정답이지만 형식 위반
- **0.0**: 오답

거기에 자연어 피드백과 `side_info` 사전을 함께 돌려준다. 예시 평가 함수는 이렇다.

```python
def evaluate(candidate: dict, example: dict):
    system = build_system_prompt(candidate)
    raw = call_task_lm(system, example["question"])
    gold = example["answer"]
    fmt_val, last_val = parse_answers(raw)

    if fmt_val is not None and fmt_val == gold:
        score, fb = 1.0, "Correct and correctly formatted."
    elif fmt_val is not None and fmt_val != gold:
        score, fb = 0.0, (
            f"WRONG ANSWER. You output '#### {fmt_val}' but the "
            f"correct answer is {gold}. Re-check the arithmetic."
        )
    # ... 형식 위반·미출력 분기 등

    side_info = {
        "feedback": fb,
        "problem": example["question"],
        "gold_answer": gold,
        "model_output": raw[:500],
    }
    return score, side_info
```

리플렉션 모델은 이 묶음을 보고 "어디서 산수가 어긋났는지", "왜 `####` 줄이 빠졌는지" 같은 진단을 직접 적는다. 0이라는 숫자만 있으면 절대 못 하는 일이다.

## 12 + 6, 홀드아웃 검증

데이터셋은 18문항짜리 결정론적 산수 벤치마크다. 할인 계산, 다구간 이동거리, 지갑 잔액, 연쇄 연산 네 종류로 만든다. 18문항 중 12개는 학습, 6개는 검증에 둔다.

학습셋으로만 최적화를 돌리고, 검증셋은 베이스라인 시드와 진화된 후보를 같은 조건에서 비교하는 데 쓴다. 학습셋에 과적합된 프롬프트는 여기서 바로 들통난다. 평가 결과는 `avg_score`와 `exact_correct+formatted` 두 수치로 찍힌다. 점수가 올랐어도 형식 일치가 안 됐다면 실전에서는 쓸 수 없는 프롬프트라는 뜻이다.

## 엔진 설정과 예산 통제

`optimize_anything` 호출은 엔진과 리플렉션 두 블록으로 갈린다.

```python
config = GEPAConfig(
    engine=EngineConfig(
        max_metric_calls=100,
        max_workers=4,
        parallel=True,
        display_progress_bar=True,
        seed=0,
    ),
    reflection=ReflectionConfig(reflection_lm="openai/gpt-4.1"),
)

result = optimize_anything(
    seed_candidate=seed_candidate,
    evaluator=evaluate,
    dataset=trainset,
    valset=valset,
    objective=objective,
    background=background,
    config=config,
)
```

`max_metric_calls=100`이 예산을 묶는다. 1~4분 안에 끝나고, 비용 폭발 없이 후보들의 계보(부모-자식 관계)와 검증 점수 추이를 한눈에 볼 수 있다. 더 깊게 가고 싶으면 이 숫자를 키우거나 리플렉션 모델을 더 강한 것으로 바꾸면 된다.

## 목적과 배경을 글로 적어 넘긴다

튜토리얼이 강조하는 또 하나의 디테일은 `objective`와 `background`를 자연어로 명시해 넘긴다는 점이다. 예를 들어 `objective`는 "작은 LLM이 다단계 산수를 안정적으로 풀고, 마지막 줄을 정확히 `#### <integer>` 형식으로 끝내도록 시스템 프롬프트를 진화시켜라"라고 적는다. 채점 근거도 함께 적는다: "1.0은 형식 일치 정답, 0.5는 숫자만 맞은 경우, 0.0은 오답. 자주 보이는 실패는 형식 누락과 다단계 산수의 자릿수 오류"라는 식이다.

리플렉션 모델은 점수만 보면 추측하지만, 이런 메타 문장이 있으면 진단의 방향이 좁아진다. 사람이 코드 리뷰어에게 "이 PR은 마이그레이션 안전성이 핵심이야"라고 한 줄 알려주는 것과 같은 효과다.

## 실무자가 볼 핵심 포인트

- **프롬프트는 사전이다**: 지시·형식·예시 등 역할별 키로 나누면 회귀 디버깅이 쉬워진다
- **보상은 다축으로**: 점수, 카테고리, 자연어 피드백, 원본 출력을 함께 던져야 리플렉션이 일한다
- **홀드아웃 없으면 가짜**: 학습셋 점수만 높은 프롬프트는 실서비스에서 더 위험하다
- **예산을 먼저 정해라**: `max_metric_calls`로 호출 상한을 박아야 비용·시간 예측이 된다
- **약한 모델 + 강한 리플렉터**: 운영은 싼 모델로, 진화 지도는 큰 모델로 — 비용 구조가 맞는다
- **결정론적 벤치마크부터**: 정답을 코드로 만들 수 있는 토이 태스크에서 루프를 먼저 검증한 뒤 실문제로 옮긴다

## 원문 출처

*Sana Hassan, "Building Reflective Prompt Optimization with GEPA: Multi-Component Prompts, Structured Feedback, and Held-Out Validation", MarkTechPost, 2026-06-07.* <https://www.marktechpost.com/2026/06/07/building-reflective-prompt-optimization-with-gepa-multi-component-prompts-structured-feedback-and-held-out-validation/>
