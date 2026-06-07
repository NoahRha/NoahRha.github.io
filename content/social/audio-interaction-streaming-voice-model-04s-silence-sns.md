---
title: "Audio-Interaction 오픈소스 음성 모델 SNS 패키지"
date: 2026-06-08T02:09:00+09:00
blog_slug: "audio-interaction-streaming-voice-model-04s-silence"
blog_url: "https://noahrha.github.io/LLM-info/audio-interaction-streaming-voice-model-04s-silence/"
source_url: "https://the-decoder.com/new-open-source-voice-model-listens-nonstop-and-decides-every-0-4-seconds-whether-to-speak-or-stay-silent/"
image_style: "oil"
image_model_policy: "gpt-image-2 primary; Minimax fallback only"
threads_image: "/images/audio-interaction-streaming-voice-model-04s-silence/audio-interaction-streaming-voice-model-04s-silence-threads-comic.png"
instagram_images:
  - "/images/audio-interaction-streaming-voice-model-04s-silence/card-01.png"
  - "/images/audio-interaction-streaming-voice-model-04s-silence/card-02.png"
  - "/images/audio-interaction-streaming-voice-model-04s-silence/card-03.png"
  - "/images/audio-interaction-streaming-voice-model-04s-silence/card-04.png"
  - "/images/audio-interaction-streaming-voice-model-04s-silence/card-05.png"
---

## Threads

P1
듣다가 말한다, 오픈소스 음성 모델이 한 발 나아갔습니다.

중국·홍콩·싱가포르 연구진이 공개한 Audio-Interaction은 0.4초마다 “지금 말할지, 그냥 들을지”를 모델이 직접 결정합니다. 파라미터 30억 개, Apache 2.0 라이선스입니다.

P2
첫 응답까지 평균 392ms입니다.

같은 모델이라도 처리 파이프라인을 직렬로 짜면 831ms로 늘어났습니다. 큐 기반 병렬 구조와 0.4초 세그먼트가 함께 만든 결과입니다.

P3
대화·번역·전사·환경음 인식이 한 모델에 들어갑니다.

“녹음 종료 버튼이 달린 받아쓰기 기계”로 불리던 기존 음성 LLM 구조에서, 끊김 없이 듣고 응답 시점을 스스로 결정하는 인터페이스로 한 칸 이동한 셈입니다.
https://noahrha.github.io/LLM-info/audio-interaction-streaming-voice-model-04s-silence/

## Instagram Caption

오픈소스 음성 모델 Audio-Interaction이 공개됐습니다. 0.4초마다 듣고 “말할지 침묵할지”를 모델이 직접 결정하는 구조입니다.

큐 기반 병렬 처리로 첫 응답까지 평균 392ms. 같은 모델을 직렬로 굴리면 831ms까지 늘어났습니다. 같은 가중치라도 파이프라인 설계가 음성 비서의 체감 속도를 가른다는 뜻입니다.

대화, 번역, 전사, 환경음 인식이 한 모델 안에서 같은 토큰 체계로 처리됩니다. Apache 2.0 라이선스라 자체 음성 비서나 회의 도구의 베이스라인으로도 검토해볼 만합니다.

🔗 자세한 글은 블로그에서 확인하세요.

#AudioInteraction #오픈소스AI #음성모델 #실시간대화 #Qwen

## Instagram Slides

1장: 끊김 없이 듣는 오픈소스 음성 모델 Audio-Interaction이 공개됐습니다
2장: 0.4초마다 모델이 직접 말할지 들을지 결정합니다
3장: 큐 기반 병렬 구조로 첫 응답까지 평균 392ms를 만들어냈습니다
4장: StreamAudio-2M 약 30만 시간 학습 데이터가 모델을 떠받칩니다
5장: 음성 AI의 다음 차별점은 “언제 말할지”를 모델이 결정하는 능력입니다

## Facebook

오픈소스 음성 모델 Audio-Interaction이 등장했습니다. 중국·홍콩·싱가포르 연구진이 만들었고, 파라미터 30억 개로 Apache 2.0 라이선스가 적용됐습니다.

가장 큰 특징은 0.4초마다 모델이 직접 “지금 말할지, 더 들을지”를 결정한다는 점입니다. 큐 기반 병렬 처리 구조 덕분에 첫 응답까지 평균 392ms를 달성했고, 같은 모델을 직렬로 굴리면 같은 작업이 831ms까지 늘어났습니다. 같은 가중치라도 파이프라인 설계가 음성 비서의 체감 속도를 가른다는 뜻입니다.

대화, 번역, 전사, 환경음 인식까지 한 모델 안에서 같은 토큰 체계로 처리됩니다. “녹음 종료 버튼이 달린 받아쓰기 기계”로 불리던 기존 음성 LLM 구조에서 한 칸 더 사람과 가까운 인터페이스로 이동했습니다.

▶ https://noahrha.github.io/LLM-info/audio-interaction-streaming-voice-model-04s-silence/

#AudioInteraction #오픈소스AI #음성모델 #실시간대화 #Qwen
