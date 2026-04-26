---
title: "Claude Code가 정말 나빠졌던 이유: Anthropic이 밝힌 세 가지 원인"
date: 2026-04-26T16:41:00+09:00
draft: false
tags:
  - Claude Code
  - Anthropic
  - AI 코딩 도구
  - Claude Sonnet
  - Claude Opus
  - Reasoning Effort
categories:
  - AI 개발
  - 번역
summary: "Anthropic이 밝힌 Claude Code 품질 저하의 세 가지 원인과 수정 일정을 시간순으로 정리했다."
---

# Claude Code가 정말 나빠졌던 이유: Anthropic이 밝힌 세 가지 원인

최근 한 달 사이 Claude Code를 쓰면서 “예전보다 답답해졌다”, “맥락을 자꾸 잊는다”, “코딩 품질이 떨어진 것 같다”고 느낀 사용자가 적지 않았습니다. 단순한 기분 탓은 아니었습니다.

XDA Developers에 따르면, Anthropic은 최근 **“An update on recent Claude Code quality reports”**라는 글을 통해 Claude Code 품질 저하의 원인을 공개했습니다. 핵심은 세 가지였습니다. 기본 추론 강도 변경, thinking 기록 삭제 버그, 그리고 지나치게 짧은 답변을 유도한 시스템 프롬프트입니다.

## 1. 3월 4일: 기본 추론 강도를 high에서 medium으로 낮췄다

첫 번째 문제는 3월 4일 시작됐습니다. Claude Code의 기본 reasoning effort, 즉 추론 강도가 기존 **high**에서 **medium**으로 변경된 것입니다.

Anthropic이 이렇게 바꾼 이유는 응답 지연 때문이었습니다. 높은 추론 강도에서는 작업 시간이 길어졌고, 일부 사용자는 앱이 멈춘 것처럼 느꼈습니다. 그래서 기본값을 medium으로 낮췄지만, 결과적으로 Claude Code의 문제 해결 능력과 코딩 품질이 제한됐습니다.

사용자들은 오히려 high를 기본값으로 두고, 필요할 때 직접 낮추는 방식을 더 선호했습니다. Anthropic은 이를 반영해 **4월 7일 기본값을 다시 high로 복구**했습니다.

## 2. 3월 26일: thinking 기록 삭제 버그가 발생했다

두 번째 문제는 더 미묘하지만 치명적이었습니다. 3월 26일, Claude Sonnet 4.6과 Opus 4.6에서 이전 thinking 기록이 잘못 삭제되는 버그가 나타났습니다.

원래 이 기능은 대화가 한 시간 이상 멈췄다가 다시 시작될 때, 토큰 사용량을 줄이기 위해 오래된 thinking 내용을 정리하는 목적이었습니다. 그런데 버그 때문에 이 정리가 **매 턴마다** 발생했습니다.

그 결과 Claude Code는 이전 맥락을 제대로 유지하지 못했고, 이미 한 말을 반복하거나 작업 흐름을 잊는 문제가 생겼습니다. 사용자가 보기에는 “왜 갑자기 기억을 못 하지?”라는 느낌을 받을 수밖에 없었습니다.

Anthropic은 이 문제를 **4월 10일 수정**했다고 밝혔습니다.

## 3. 4월 16일: 너무 짧게 답하라는 프롬프트가 코딩 품질을 떨어뜨렸다

세 번째 문제는 4월 16일 적용된 시스템 프롬프트 변경이었습니다. Anthropic은 Claude Code의 장황한 답변을 줄이기 위해 다음과 같은 길이 제한 지시를 넣었습니다.

> “도구 호출 사이의 텍스트는 25단어 이하로 유지하고, 최종 응답은 작업에 더 자세한 설명이 필요한 경우를 제외하고 100단어 이하로 유지하라.”

문제는 이 제한이 다른 프롬프트 조정과 맞물리면서 코딩 품질에 악영향을 줬다는 점입니다. 코딩 작업은 때로 충분한 설명, 판단 근거, 단계적 사고가 필요합니다. 그런데 모델이 지나치게 짧게 답하려다 보니 중요한 맥락이나 설명이 빠질 수 있었습니다.

Anthropic은 이 변경 역시 문제가 있었다고 보고, **4월 20일 되돌리거나 수정**했습니다. XDA 원문은 4월 20일 이후 세 가지 주요 불편 요소가 모두 해결된 상태라고 설명합니다.

## 결론: AI 코딩 도구의 품질은 ‘모델’만의 문제가 아니다

이번 사례는 Claude Code의 품질 저하가 단순히 모델 성능 문제만은 아니라는 점을 보여줍니다. 기본 추론 강도, 대화 기록 처리 방식, 시스템 프롬프트 한 줄 같은 운영 설정도 실제 개발 경험에 큰 영향을 줍니다.

특히 AI 코딩 도구는 단순 질의응답보다 맥락 유지와 깊은 추론이 중요합니다. 응답 속도를 높이거나 답변을 짧게 만드는 최적화가 오히려 품질을 떨어뜨릴 수 있다는 점도 확인됐습니다.

Claude Code를 사용하다가 최근 이상함을 느꼈다면, 그 감각은 틀리지 않았습니다. 다만 Anthropic이 원인을 공개하고 수정 일정을 명확히 밝혔다는 점은 긍정적입니다.

앞으로 AI 코딩 도구를 평가할 때는 모델명뿐 아니라, 어떤 기본 설정과 시스템 프롬프트로 운영되는지도 함께 봐야 할 것 같습니다.

---

출처: [XDA Developers - You weren't imagining it — Claude Code really did get worse, and Anthropic just explained why](https://www.xda-developers.com/you-werent-imagining-it-claude-code-really-did-get-worse-and-anthropic-just-explained-why/)
