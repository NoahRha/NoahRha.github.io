---
title: "허깅페이스가 매주 huggingface_hub를 출시하는 법 — AI 초안과 사람 검수, 그 사이의 결정론적 가드"
date: 2026-06-23T18:05:00+09:00
draft: false
description: "허깅페이스가 huggingface_hub 라이브러리 출시를 4~6주에서 매주로 단축한 비결. AI는 초안을 쓰고, 결정론적 스크립트가 누락을 잡고, 사람이 마지막에 다듬는 구조를 그대로 정리합니다."
cover:
  image: "/images/huggingface-hub-weekly-release-ai-ci/huggingface-hub-weekly-release-ai-ci-cover.png"
  alt: "허깅페이스 hub 출시 파이프라인을 상징하는 이미지"
  caption: ""
tags:
  - HuggingFace
  - 릴리즈자동화
  - AI에이전트
  - GitHubActions
  - 오픈소스
  - PyPI
  - OpenCode
categories:
  - LLM-info
---

## 핵심 요약

- 허깅페이스는 `huggingface_hub` 출시 주기를 4~6주에서 **매주 1회**로 줄였습니다.
- 기계적인 일(태그·버전 범프·PyPI 업로드·다운스트림 테스트 브랜치)은 GitHub Actions가 다 합니다.
- 머리 쓰는 일(릴리즈 노트, 슬랙 공지) 초안은 오픈 웨이트 모델 GLM-5.2가 OpenCode 위에서 작성합니다.
- 핵심은 "신뢰하되 검증한다". 결정론적 스크립트가 빠진 PR·이상한 PR을 잡아내고, 사람은 톤만 다듬습니다.
- 한 번 출시에 드는 추론 비용은 **약 0.25달러**. 비용보다 사람 시간이 훨씬 비싸다는 사실이 명확해졌습니다.

## 출시 한 번이 반나절을 잡아먹던 시절

`huggingface_hub`는 원래 4~6주에 한 번씩만 새 버전이 나왔습니다. CI는 태그가 푸시되면 PyPI에 올려주는 정도였고, 정작 사람 손이 가는 일이 따로 있었습니다. 릴리즈 브랜치 만들고, `__init__.py` 버전 올리고, 태그 달고, 다운스트림 라이브러리(`transformers`, `datasets`, `diffusers` 등)에 RC를 핀해 테스트 브랜치를 여는 것까지.

가장 무거운 건 릴리즈 노트였습니다. 한 버전에 머지된 PR 수십 개를 주제별로 묶어 사람 말투로 다시 풀어 써야 했죠. `git log` 덤프처럼 보이지 않게 만들려면 결국 몇 시간씩 집중해서 글을 써야 했습니다. 여기에 슬랙 공지까지 더하면, 마이너 릴리즈 한 번에 반나절이 그대로 사라졌습니다.

## 일을 두 종류로 나눈다

허깅페이스 팀은 발상을 단순하게 잡았습니다. "기계가 할 일"과 "머리를 써야 할 일"을 분리한 겁니다.

기계적인 일은 GitHub Actions에 맡깁니다. 버전 범프, 커밋, 태그, 푸시, 다운스트림 테스트 브랜치 열기, 출시 후 `dev0`로 되돌리는 PR까지. 누가 머리를 쓸 필요가 없는 작업입니다.

남는 건 판단이 필요한 글쓰기입니다. 무엇을 강조할지, 어떤 말투로 쓸지, 어떤 PR을 한 줄로 묶을지. 여기서 AI가 들어옵니다. 빈 페이지를 몇 초 만에 그럴듯한 초안으로 바꿔주는 일은 모델이 잘 합니다. 다만 "그럴듯하게 틀린" 초안은 차라리 없느니만 못하니까, 안전장치가 필요합니다.

## 모든 부품을 오픈으로 — 갈아 끼울 수 있게

설계할 때 단 하나의 제약을 걸었다고 합니다. **어떤 부품도 다른 메인테이너가 자기 환경에서 그대로 돌릴 수 있어야 한다.** 그래서 닫힌 API 모델도, 독점 릴리즈 플랫폼도 쓰지 않았습니다.

스택은 이렇게 됩니다.

| 부품 | 역할 |
|------|------|
| GitHub Actions | 전체 릴리즈를 지휘 |
| [OpenCode](https://opencode.ai/) | 모델을 구동하는 에이전트 런타임 |
| 오픈 웨이트 모델 ([Z.ai GLM-5.2](https://huggingface.co/zai-org/GLM-5.2)) | 릴리즈 노트와 슬랙 공지 초안 작성 |
| HF Inference Providers | 모델을 서비스로 제공 |
| PyPI Trusted Publishing | 패키지 업로드 |

원칙은 두 가지입니다. 부품은 전부 갈아 끼울 수 있어야 하고, **모델은 초안, 결정은 사람**.

![자동화된 출시 파이프라인 일러스트](/images/huggingface-hub-weekly-release-ai-ci/huggingface-hub-weekly-release-ai-ci-body-01.png)

## 파이프라인 한 바퀴

전체 워크플로는 `.github/workflows/release.yml` 한 파일에 들어 있고, Actions UI에서 손으로 트리거합니다. 입력은 단 하나, 릴리즈 타입입니다. `minor-prerelease`로 RC를 자르고, `minor-release`로 RC를 정식 버전으로 올리고, `patch-release`로 핫픽스를 냅니다.

흐름을 풀어 쓰면 다음과 같습니다. 다음 버전 계산 → 릴리즈 브랜치 정리 → `__version__` 범프, 커밋, 태그, 푸시 → PyPI 업로드(본 패키지와 `hf` CLI 동시) → 릴리즈 노트 초안 → 다운스트림 테스트 브랜치 열기 → 슬랙 공지 초안 → 원본 초안과 사람 수정본을 Hugging Face Bucket에 함께 보관 → 정식 릴리즈 후 `main`을 다음 `dev0`로 되돌리는 PR → 이번 버전에 포함된 모든 PR에 "이 PR은 vX.Y.Z에 포함되었습니다" 코멘트 → CLI 스킬 문서 동기화 → 슬랙 스레드에 단계별 ✅/❌ 보고.

남은 수동 작업은 두 가지뿐입니다. 드래프트로 올라온 릴리즈 노트를 검토해 발행하기, 그리고 슬랙 공지를 다듬어 올리기. 다른 곳은 사람이 손댈 일이 없습니다.

## "신뢰하되 검증한다" — 한 줄 코드가 모델을 잡는다

AI 릴리즈 노트에서 가장 무서운 실패는 따로 있습니다. 모델이 PR 하나를 슬쩍 빼먹거나, 이번 버전과 무관한 PR을 끼워 넣는 경우입니다. "거의 맞는 변경 이력"은 사실 아무도 다시 안 봐서 더 위험합니다.

이걸 막는 방식이 깔끔합니다. 모델을 돌리기 전에, 결정론적 스크립트가 이번 버전에 포함된 PR 번호를 먼저 추출해 매니페스트로 저장합니다.

```python
PR_NUMBER_PATTERN = re.compile(r"\(#(\d+)\)$")

pr_numbers = [
    int(m.group(1))
    for commit in commits_since_last_tag
    if (m := PR_NUMBER_PATTERN.search(commit.title))
]
save_manifest(pr_numbers)  # 진실의 원천
```

그다음에 모델이 초안을 씁니다. 마지막에 그 초안에서 PR 참조(`#1234`)를 다시 뽑아내, 매니페스트와 차집합을 계산합니다.

```python
expected = set(load_manifest())
found    = extract_pr_refs(notes_md)

missing = expected - found       # 모델이 빼먹은 것
extra   = found - expected       # 다른 버전에 속한 것
```

차이가 0이 아니면 그냥 실패시키지 않습니다. 빠진 PR과 잘못 들어간 PR을 다시 에이전트에게 넘겨, **그 PR만 고치도록** 다시 요청합니다. 일치할 때까지 정해진 횟수만큼 반복합니다.

```python
for _ in range(MAX_ITERATIONS):
    missing, extra = validate(notes)
    if not missing and not extra:
        break
    run_agent_fix(missing_prs=missing, extra_prs=extra)
```

비결정적인 모델을 결정론적인 가드로 감싸는 패턴입니다. 모델은 문장을 잘 쓰고, 코드는 빠진 게 없는지 잘 셉니다. 각자 잘하는 걸 시킵니다.

![모델 초안과 결정론적 검증을 함께 두는 구조 일러스트](/images/huggingface-hub-weekly-release-ai-ci/huggingface-hub-weekly-release-ai-ci-body-02.png)

## 모델이 사실을 지어내지 않게 — 진짜 코드를 물려주기

완전성은 그렇게 막았다 치고, 정확성은 또 다른 문제입니다. PR 제목만 보고 요약하는 모델은 새 CLI 명령어 예시를 자신 있게 지어내곤 합니다.

그래서 PR 메타데이터를 가져올 때 문서 변경분도 같이 끌고 옵니다. PR이 건드린 `docs/` 아래 `.md` 파일의 unified diff를 그대로 모델 컨텍스트에 넣어 줍니다.

```python
def fetch_doc_diffs(pr):
    return [
        {"filename": f.filename, "status": f.status, "patch": f.patch}
        for f in pr.get_files()
        if f.filename.startswith("docs/") and f.filename.endswith(".md") and f.patch
    ]
```

이렇게 하면 모델이 "여기 새 CLI 명령이 추가됐습니다"라고 쓸 때, PR 작성자가 실제로 문서에 적은 예시를 인용하게 됩니다. 모델에게는 좁은 작업을 주고, 진짜 자료를 손에 쥐어 주는 것. 자주 통하는 패턴입니다.

프롬프트 자체도 레포 안에 [`.opencode/skills/hf-release-notes`](https://github.com/huggingface/huggingface_hub/tree/main/.opencode/skills/hf-release-notes) 폴더로 들어 있습니다. `SKILL.md`와 템플릿 같은 작은 마크다운 파일들이고, 신입 메인테이너에게 주는 온보딩 문서처럼 읽힙니다. 사실 그게 정확한 비유입니다.

## 사람이 들어오는 자리

RC가 올라오면 GitHub에 드래프트 릴리즈가 자동으로 만들어집니다. 안에는 모델의 첫 초안이 들어 있고, 여기서부터 사람의 일입니다.

리뷰어가 한 번 쭉 읽으며 톤과 강조점을 다듬고, 모델이 과하게 키우거나 묻어버린 부분을 고칩니다. 그 다음에야 `minor-release` 워크플로를 돌려 RC를 정식 버전으로 승격합니다.

반나절짜리 글쓰기가 15분짜리 편집으로 줄어든 게 핵심입니다.

기록도 같이 남깁니다. RC 시점에 손대지 않은 원본 초안을, 정식 릴리즈 시점에 사람이 수정한 최종본을 각각 Hugging Face Bucket에 올립니다.

```bash
hf cp release_notes_raw.txt    "hf://buckets/huggingface/releases/huggingface_hub/${V}/release_notes_raw.txt"
hf cp release_notes_edited.txt "hf://buckets/huggingface/releases/huggingface_hub/${V}/release_notes_edited.txt"
```

"모델이 쓴 것"과 "사람이 고친 것"이 매주 한 쌍씩 쌓이는 셈입니다. 나중에 이 데이터셋으로 에이전트 스킬을 다시 튜닝할 수 있습니다.

## 공급망 공격 막는 배관 — PyPI 토큰 없이

릴리즈 프로세스를 손보는 김에 공급망 보안도 같이 올렸습니다.

PyPI에는 토큰을 두지 않습니다. [Trusted Publishing](https://docs.pypi.org/trusted-publishers/) 방식이라, GitHub이 이 워크플로 전용으로 발급한 단기 OIDC 토큰을 PyPI가 검증합니다. 아티팩트마다 [PEP 740](https://peps.python.org/pep-0740/) Sigstore 어테스테이션까지 자동으로 붙습니다. 장기 비밀이 없으니 유출도 만료도 신경 쓸 일이 없습니다.

```yaml
permissions:
  id-token: write
  attestations: write
- uses: pypa/gh-action-pypi-publish@v1.14.0
  with:
    attestations: true
```

에이전트 런타임도 그대로 신뢰하지 않습니다. `curl | bash`로 최신 버전을 받지 않고, 버전을 핀한 다음 SHA256까지 확인합니다.

```bash
curl -fsSL https://opencode.ai/install | bash -s -- --version "${OPENCODE_VERSION}"
echo "${OPENCODE_SHA256}  $(which opencode)" | sha256sum -c -
```

오픈 도구라고 해서 막 쓰지는 않는다는 자세입니다.

## 결과 — 비용 0.25달러, 주 1회 출시

전체 릴리즈 한 번에 모델 호출 비용은 **약 0.25달러**입니다. PR 20~40개를 다루고 프롬프트를 몇 번 다시 돌려도 그 정도입니다. 오픈 웨이트 모델을 종량제로 굴리니, 매주 던지는 질문이 "이번 주에 출시할 만한 게 있나?" 한 줄로 단순해졌습니다. 답은 매번 "있다" 쪽에 가깝습니다.

부수 효과가 더 흥미롭습니다.

- **릴리즈 노트 품질이 올라갔습니다.** 초안이 늘 존재하니 리뷰 시간이 다듬기에 들어갑니다. 묶음이 더 일관되고, 빠뜨리는 항목도 줄었습니다.
- **다운스트림 깨짐이 더 일찍 잡힙니다.** RC가 매주 나오니, 다운스트림 통합 문제가 짧은 주기로 드러납니다.
- **컨트리뷰터 피드백 루프가 짧아졌습니다.** 닫힌 PR에 "이 수정은 vX.Y.Z에 들어갔습니다"라는 자동 코멘트가 달리니, 사용자가 어느 버전부터 고쳐졌는지 바로 알 수 있게 됐습니다. 예상보다 큰 효과였다고 합니다.

## 실무자가 볼 핵심 포인트

- **자동화의 선을 정확히 긋는다.** 기계적인 절차는 무조건 YAML로, 판단이 필요한 글쓰기는 모델 초안 + 사람 검수로 분리하세요.
- **모델을 결정론으로 감싼다.** "AI에게 맡긴다"가 아니라 "AI 초안 → 결정론적 검증 → 빠진 부분만 다시 요청"의 루프가 본질입니다. 다른 도메인에도 그대로 옮겨 쓸 수 있습니다.
- **모델에게 진짜 자료를 쥐어 준다.** PR 제목 대신 실제 `docs/` diff를 넣어 주면 가짜 코드 예시가 거의 사라집니다.
- **프롬프트는 레포에 두고 버전 관리한다.** `SKILL.md` 형태로 두면 변경 이력이 남고, 다른 메인테이너가 그대로 포크할 수 있습니다.
- **공급망 비밀은 줄인다.** PyPI Trusted Publishing(OIDC), 에이전트 런타임 SHA256 핀처럼 장기 비밀이 없는 배관을 먼저 고르세요.
- **원본 초안과 최종본을 같이 저장한다.** 모델이 쓴 것과 사람이 고친 것을 한 쌍으로 남기면, 시간이 지난 뒤 스킬을 다시 튜닝할 데이터셋이 자동으로 쌓입니다.
- **포크 가능한 형태로 만든다.** 다운스트림 목록·톤·슬랙 라우팅처럼 회사마다 다른 부분은 변수화하고, 신뢰-검증 루프는 그대로 가져갈 수 있게 둡니다.

## 원문 출처

[원문 보기](https://huggingface.co/blog/huggingface-hub-release-ci) — Lucain Pouget(Wauplin), Célina Hanouti(celinah), Hugging Face Blog, 2026-06-23
