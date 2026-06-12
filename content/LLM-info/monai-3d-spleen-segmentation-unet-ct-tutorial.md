---
title: "MONAI로 비장 CT 분할 파이프라인 만들기: 3D UNet 실전 코드"
date: 2026-06-12T20:18:10+09:00
draft: false
description: "MONAI 1.5.2와 3D UNet으로 의료 CT 볼륨에서 비장을 분할하는 전 과정을 한 번에 따라 해보는 실습 노트입니다. 데이터셋 다운로드부터 전처리, 학습, 검증, 결과 시각화까지 코드 단위로 정리했습니다."
cover:
  image: "/images/monai-3d-spleen-segmentation-unet-ct-tutorial/cover.png"
  alt: "MONAI로 만드는 3D 비장 분할 파이프라인"
  caption: "원문 MarkTechPost 기사 대표 이미지"
tags:
  - MONAI
  - 의료영상
  - 3D UNet
  - CT 분할
  - PyTorch
  - 딥러닝 튜토리얼
  - 의료 AI
categories:
  - AI 튜토리얼
---

의료 영상에서 장기를 잘라내는 일은 늘 까다롭습니다. 2D 사진과 달리 CT는 한 환자당 수백 장의 슬라이스로 이루어진 3차원 데이터고, 좌표계도 환자마다 다르고, 픽셀 값도 보정이 필요합니다. 그래서 의료 영상 딥러닝을 처음 시작하면 "데이터를 어떻게 정리해야 하나"에서부터 막히는 경우가 많습니다.

이번에 소개할 자료는 PyTorch 기반 의료 영상 전용 라이브러리 **MONAI 1.5.2**로 비장(spleen) CT 분할 파이프라인을 처음부터 끝까지 만드는 실습 코드입니다. 데이터셋 다운로드, 좌표 정렬, 강도 보정, 패치 샘플링, 3D UNet 학습, 슬라이딩 윈도우 추론, 결과 시각화까지 한 번에 돌릴 수 있게 짜여 있어 입문 자료로 꽤 깔끔합니다.

## 핵심 요약

- **데이터셋**: Medical Segmentation Decathlon Task09 Spleen. MONAI `DecathlonDataset`이 다운로드와 분할까지 자동으로 처리합니다.
- **모델**: 3D UNet. 비장과 배경을 가르는 이진 분할 문제입니다.
- **전처리 파이프라인**: 방향 정렬(`Orientationd`), 복셀 간격 정규화(`Spacingd`), 강도 윈도잉(`ScaleIntensityRanged`), 전경 자르기(`CropForegroundd`), 96×96×96 패치 샘플링.
- **학습 설정**: DiceCE 손실 + AdamW(lr 1e-4, weight decay 1e-5) + Cosine Annealing 스케줄러 + PyTorch AMP 혼합 정밀도.
- **검증**: 슬라이딩 윈도우 추론(중첩 0.5)으로 전체 볼륨을 훑고, 배경을 뺀 평균 Dice 점수를 추적합니다.
- **빠른 실행 모드**: `QUICK_RUN=True`로 두면 15에포크 / 캐시 8, 풀 학습은 200에포크 / 캐시 24로 자동 전환됩니다.

## 왜 MONAI인가

의료 영상은 일반 비전 모델을 그대로 갖다 붙이기 어렵습니다. NIfTI 파일을 읽어야 하고, 머리·발 방향(RAS)을 맞춰야 하고, HU(Hounsfield Unit) 값으로 윈도잉을 해줘야 합니다. 이걸 다 직접 구현하면 코드가 금세 수백 줄로 불어납니다.

MONAI는 이런 의료 영상 특유의 전처리, 데이터 로더, 손실 함수, 추론 도구를 PyTorch 위에 얹어둔 라이브러리입니다. 실제로 이번 실습에서도 `LoadImaged → EnsureChannelFirstd → Orientationd → Spacingd → ScaleIntensityRanged → CropForegroundd` 한 줄 한 줄이 전부 의료 영상 표준 절차에 대응됩니다. 일반 PyTorch만으로 짜면 한참 걸릴 코드가 `Compose`로 짧게 정리됩니다.

## 데이터에서 모델까지 — 코드 흐름

전체 흐름은 크게 다섯 덩어리로 나뉩니다.

1. **환경 준비**. `pip install monai[nibabel,tqdm,matplotlib]==1.5.2`로 의료 영상 의존성까지 한 번에 설치합니다. GPU가 있으면 자동으로 CUDA를 잡고, 없으면 CPU로 떨어집니다.
2. **데이터 로드와 변환**. `DecathlonDataset(task="Task09_Spleen", ...)`로 비장 데이터셋을 받습니다. 학습 변환에는 랜덤 플립, 90도 회전, 강도 시프트가 들어가고, 검증 변환에는 동일한 전처리만 적용해 결과 재현성을 지킵니다.
3. **모델과 학습 도구**. `monai.networks.nets.UNet`으로 3D UNet을 만들고, `DiceCELoss(to_onehot_y=True, softmax=True)`로 손실을, `DiceMetric(include_background=False, reduction="mean")`으로 평가 지표를 세팅합니다. `torch.amp`의 `GradScaler`로 혼합 정밀도를 켭니다.
4. **학습 루프**. 매 에포크마다 패치를 뽑아 학습하고, 3 에포크마다 검증을 돌립니다. 평균 Dice가 최고치를 갱신할 때만 `best_spleen_unet.pth`로 가중치를 저장하기 때문에, 중간에 끊겨도 가장 좋은 모델은 남습니다.
5. **결과 확인**. 학습이 끝나면 loss와 Dice 곡선을 그리고, 베스트 체크포인트를 다시 불러와 검증 볼륨 한 장에 슬라이딩 윈도우 추론을 돌립니다. CT 단면, 정답 마스크, 모델 예측을 가로로 나란히 띄워 눈으로 직접 비교할 수 있게 합니다.

## 입문자가 놓치기 쉬운 디테일

코드를 그냥 복붙해도 돌긴 하지만, 두세 줄짜리 설정에 의미가 꽤 많이 숨어 있습니다.

- **패치 크기 96×96×96**. CT 한 볼륨 전체를 한꺼번에 GPU에 올리면 메모리가 폭발합니다. `RandCropByPosNegLabeld`가 양성·음성 비율을 맞춰 작은 패치만 뽑아 학습합니다.
- **`CropForegroundd`**. 배경이 너무 큰 슬라이스를 잘라내 학습 효율을 올립니다. 의료 영상에서 자주 쓰는 트릭이에요.
- **`include_background=False`**. 비장 분할은 배경이 압도적으로 많아 Dice가 부풀려지기 쉽습니다. 배경을 빼야 진짜 비장 영역 성능만 봅니다.
- **슬라이딩 윈도우 추론(`overlap=0.5`)**. 검증 때는 학습과 달리 볼륨 전체를 봐야 합니다. 패치를 겹쳐 가며 훑고 결과를 평균 내서, 패치 경계 흔적을 줄입니다.
- **체크포인트는 베스트만**. 검증 Dice가 갱신될 때만 저장하기 때문에, 디스크 낭비 없이 모델 선택 작업도 같이 끝납니다.

## 실무자가 볼 핵심 포인트

- 의료 영상 파이프라인은 보통 전처리에서 70%가 갈리는데, MONAI가 그 부분을 표준화해 줍니다. 같은 코드 구조로 간(Task03), 췌장(Task07), 폐(Task06)도 바로 바꿔 끼울 수 있어요.
- 빠른 검증이 필요할 때는 `QUICK_RUN=True`로 15에포크만 돌려 흐름이 깨지지 않는지 먼저 확인하고, 그다음에 200에포크 풀 학습으로 넘어가는 패턴이 안전합니다.
- DiceCE 손실은 클래스 불균형에 강하지만, 비장처럼 작은 장기는 결국 패치 샘플링 비율(`num_samples`, pos/neg)에서 성능이 더 크게 좌우됩니다. 하이퍼파라미터 튜닝 1순위로 두세요.
- 본 코드는 단일 GPU 단일 노드 기준입니다. 다중 GPU로 넘어갈 땐 MONAI `CacheDataset` 대신 `SmartCacheDataset` 또는 `PersistentDataset`을 검토하는 것이 좋습니다.
- 의료기관 실 데이터에 옮길 때는 HIPAA·개인정보보호법 관점에서 DICOM 익명화가 먼저입니다. 모델보다 데이터 파이프라인 검토에 더 많은 시간이 들 수 있습니다.

## 정리하며

MONAI 코드가 길어 보여도, 결국 핵심은 "의료 영상 전용 전처리 + 3D UNet + DiceCE + 슬라이딩 윈도우 추론" 네 가지의 조합입니다. 이 구조를 한 번 익혀두면 다른 장기, 다른 데이터셋으로 옮겨가도 손이 빠르게 따라옵니다. 처음부터 풀 학습 200에포크에 매달리지 말고, 15에포크 빠른 모드로 끝까지 굴려본 다음 본격적으로 튜닝하는 흐름을 추천합니다.

## 원문 출처

*[A Coding Implementation on MONAI for End-to-End 3D Spleen Segmentation Using UNet on Medical CT Volumes](https://www.marktechpost.com/2026/06/12/a-coding-implementation-on-monai-for-end-to-end-3d-spleen-segmentation-using-unet-on-medical-ct-volumes/) — Sana Hassan, MarkTechPost, 2026-06-12*
