---
slug: gepa-reflective-prompt-optimization
title: "GEPA: 반사형 프롬프트 최적화 — 다중 컴포넌트·구조화 피드백·홀드아웃 검증"
blog_url: https://techllm.github.io/posts/gepa-reflective-prompt-optimization/
source_url: https://www.marktechpost.com/2026/06/07/building-reflective-prompt-optimization-with-gepa-multi-component-prompts-structured-feedback-and-held-out-validation/
created_at: 2026-06-08T11:20:44+09:00
style: hand-drawing
---

## Threads (3-part)

### P1 (본문)
프롬프트 한 줄을 손으로 고치는 시대를 끝낸다는 GEPA 튜토리얼이 등장했습니다.

작업 모델은 풀고, 리플렉션 모델은 프롬프트를 고치고, 사람은 점수 함수만 정확히 적습니다.

### P2 (댓글 1)
핵심은 두 가지입니다.

1) 프롬프트를 `instructions`와 `format_rules` 같은 컴포넌트 사전으로 쪼개 함께 진화시킵니다.
2) 점수 1.0/0.5/0.0과 자연어 피드백을 한 묶음으로 던져 리플렉션이 원인을 직접 짚게 합니다.

### P3 (댓글 2)
학습 12문항·홀드아웃 6문항으로 일반화를 강제 검증하고, `max_metric_calls=100`으로 비용을 묶습니다.

작업 모델은 `gpt-4o-mini`, 리플렉션은 `gpt-4.1` — 운영은 싸게, 진화 지도는 강한 모델로.

자세한 설정과 코드 예시는 글에서 정리했습니다.
https://techllm.github.io/posts/gepa-reflective-prompt-optimization/

## Instagram Caption

GEPA로 짓는 반사형 프롬프트 최적화

프롬프트를 한 덩어리가 아니라 `instructions`와 `format_rules` 사전으로 쪼개고, 점수와 자연어 피드백을 함께 던져 리플렉션 모델이 직접 원인을 진단하도록 만듭니다.

학습 12문항·홀드아웃 6문항으로 일반화 여부를 강제 검증하고, `max_metric_calls=100`으로 비용을 1~4분 안에 묶습니다. 작업 모델은 `gpt-4o-mini`, 리플렉션은 `gpt-4.1` — 약한 모델이 풀고, 강한 모델이 프롬프트를 고친다는 분업 구조입니다.

🔗 자세한 글은 블로그에서 확인하세요.

#GEPA #프롬프트최적화 #LLM #AI에이전트 #평가

## Facebook

수동 프롬프트 튜닝 루프를 LLM 두 대에 떠넘기는 GEPA(Generic Evolutionary Prompt Adaptation) 튜토리얼을 정리했습니다.

핵심은 두 가지입니다. 첫째, 프롬프트를 `instructions`와 `format_rules` 같은 컴포넌트 사전으로 쪼개 함께 진화시킵니다. 둘째, 평가 함수는 점수 1.0/0.5/0.0과 자연어 피드백, 원본 출력을 한 묶음으로 돌려줘 리플렉션 모델이 실패 원인을 직접 짚습니다.

데이터셋은 결정론적 산수 18문항 — 12개는 학습, 6개는 홀드아웃 검증. `max_metric_calls=100`으로 호출 예산을 묶어 1~4분 안에 끝납니다. 작업 모델은 `gpt-4o-mini`로 싸게, 리플렉션은 `gpt-4.1`로 강하게. 운영 비용 구조와 진화 품질을 동시에 맞추는 분업입니다.

▶ https://techllm.github.io/posts/gepa-reflective-prompt-optimization/

#GEPA #프롬프트최적화 #LLM #AI에이전트 #평가
