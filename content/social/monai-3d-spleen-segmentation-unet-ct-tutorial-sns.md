# SNS 홍보 콘텐츠

원문 블로그: `content/LLM-info/monai-3d-spleen-segmentation-unet-ct-tutorial.md`
공개 URL: `https://noahrha.github.io/LLM-info/monai-3d-spleen-segmentation-unet-ct-tutorial/`
주제: MONAI 1.5.2와 3D UNet으로 의료 CT 볼륨에서 비장을 분할하는 엔드투엔드 실습 파이프라인

---

## Threads 3-part

### P1 본문
의료 CT에서 비장을 잘라내는 일은 늘 데이터부터 막힙니다. 좌표계가 환자마다 다르고, HU 값 보정이 필요하고, 한 환자당 수백 슬라이스를 다뤄야 하니까요.

MarkTechPost에서 MONAI 1.5.2 + 3D UNet으로 처음부터 끝까지 돌리는 실습 코드를 공개했습니다.

데이터셋 다운로드 → 전처리 → 학습 → 추론 → 시각화까지 한 노트북에 다 들어 있어요.

### P2 댓글
핵심 설정 요약:

- 데이터셋: Medical Segmentation Decathlon Task09 Spleen
- 모델: 3D UNet (이진 분할)
- 전처리: 방향 정렬, 복셀 정규화, 강도 윈도잉, 전경 자르기, 96×96×96 패치
- 손실: DiceCE
- 옵티마이저: AdamW lr 1e-4, Cosine Annealing
- AMP 혼합 정밀도 + 슬라이딩 윈도우 추론 (overlap 0.5)

QUICK_RUN 플래그로 15에포크 빠른 실행과 200에포크 풀 학습을 한 번에 토글합니다.

### P3 댓글
입문자가 놓치기 쉬운 디테일도 짚어두세요.

include_background=False가 빠지면 Dice가 부풀려져요. 비장은 전체 볼륨에서 차지하는 비율이 워낙 작거든요.

CropForegroundd, RandCropByPosNegLabeld로 양성·음성 비율을 맞추는 것도 작은 장기에서 성능을 가장 크게 좌우합니다.

같은 코드 구조 그대로 간(Task03), 췌장(Task07), 폐(Task06)로 갈아탈 수 있다는 게 MONAI의 진짜 장점입니다.

전체 흐름은 블로그에서 정리했습니다.
https://noahrha.github.io/LLM-info/monai-3d-spleen-segmentation-unet-ct-tutorial/

---

## Instagram 카드뉴스 (5컷)

**카드 1 — 후크**
의료 CT에서 장기를 잘라내는 일,
어디서부터 막히세요?

MONAI + 3D UNet 한 노트북 실습

**카드 2 — 문제 정의**
2D 이미지와 다른 3D 의료 영상

좌표계가 환자마다 다르고
HU 값 보정이 필요하고
한 환자당 수백 슬라이스

전처리에서 70%가 갈립니다

**카드 3 — MONAI의 역할**
의료 영상 전용 전처리
LoadImaged → Orientationd → Spacingd
→ ScaleIntensityRanged → CropForegroundd

복잡한 코드가 Compose 한 줄로 정리

**카드 4 — 학습 설정**
모델: 3D UNet
손실: DiceCE
옵티마이저: AdamW (1e-4)
패치: 96×96×96
AMP 혼합 정밀도

QUICK_RUN으로 15에포크 빠른 검증

**카드 5 — 실무 팁**
include_background=False 잊지 마세요
작은 장기는 패치 샘플링 비율이 1순위
같은 코드로 간·췌장·폐도 바로 교체 가능
DICOM 익명화는 모델보다 먼저

전체 정리 → 블로그에서

---

## Facebook

의료 CT에서 비장을 잘라내는 일은 보기보다 까다롭습니다. 2D 사진과 달리 한 환자당 수백 장의 슬라이스가 쌓인 3차원 볼륨이고, 좌표계도 환자마다 다르고, 픽셀 값도 HU 단위 보정이 필요합니다. 의료 영상 딥러닝 입문자가 "데이터를 어떻게 정리해야 하나"에서 막히는 이유죠.

MarkTechPost에서 MONAI 1.5.2와 3D UNet으로 끝에서 끝까지 돌아가는 비장 분할 파이프라인 실습 코드를 공개했습니다. Medical Segmentation Decathlon Task09 데이터셋을 자동으로 받아 전처리하고, DiceCE 손실 + AdamW + Cosine Annealing 스케줄러로 학습한 뒤, 슬라이딩 윈도우 추론으로 검증 Dice를 추적합니다. QUICK_RUN 플래그 하나로 15에포크 빠른 실행과 200에포크 풀 학습을 토글할 수 있어, 코드 구조를 먼저 검증하고 본격 학습으로 넘어가는 안전한 패턴이 자연스럽게 잡힙니다.

입문자에게 가장 유용한 디테일은 include_background=False 옵션과 패치 샘플링 비율입니다. 비장은 전체 볼륨에서 차지하는 영역이 매우 작아서 배경 포함 Dice는 거의 의미가 없고, 패치 뽑는 비율이 성능을 가장 크게 좌우합니다. 또 한 가지 강점은 이식성입니다. 같은 코드 구조를 그대로 간(Task03), 췌장(Task07), 폐(Task06) 데이터셋으로 교체할 수 있어 다른 장기 분할로 확장하기가 매우 빠릅니다.

자세한 흐름과 코드 해설은 블로그에서 정리했습니다.
https://noahrha.github.io/LLM-info/monai-3d-spleen-segmentation-unet-ct-tutorial/
