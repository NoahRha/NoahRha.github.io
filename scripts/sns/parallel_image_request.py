#!/usr/bin/env python3
"""v3 이미지 병렬 생성 dispatcher.

9장(커버1 + 본문2 + Threads1 + IG5) 요청을 3+3+3 배치로 자동 분할하여
imagemaker 서브에이전트에 동시 호출 (max 3 per batch). gpt-image-2 rate-limit 안전.

사용법:
    python3 parallel_image_request.py --request-json path/to/request.json
    python3 parallel_image_request.py --plan path/to/plan.json  # 9장 분할 명시
    python3 parallel_image_request.py --profile hybrid

출력:
    - 각 배치별 JSON + MD 요청서
    - 배치 실행 로그 data/parallel_image_runs.jsonl
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

KST = timezone(timedelta(hours=9))

# v3 기본 배치 (안전 모드): 3+3+3
DEFAULT_BATCH_SIZE = 3

# 9장 표준 순서 (커버 → 본문 → Threads → IG)
DEFAULT_9_PLAN = [
    # Batch 1 (T+0s)
    {"slot": "cover", "asset_type": "blog_cover_image", "label": "블로그 커버"},
    {"slot": "body-1", "asset_type": "blog_cover_image", "label": "본문 이미지 1"},
    {"slot": "threads-comic", "asset_type": "cardnews_4cut_comic", "label": "Threads 4컷 만화"},
    # Batch 2 (T+30s)
    {"slot": "body-2", "asset_type": "blog_cover_image", "label": "본문 이미지 2"},
    {"slot": "ig-slide-1", "asset_type": "cardnews_background", "label": "IG 슬라이드 1"},
    {"slot": "ig-slide-2", "asset_type": "cardnews_background", "label": "IG 슬라이드 2"},
    # Batch 3 (T+60s)
    {"slot": "ig-slide-3", "asset_type": "cardnews_background", "label": "IG 슬라이드 3"},
    {"slot": "ig-slide-4", "asset_type": "cardnews_background", "label": "IG 슬라이드 4"},
    {"slot": "ig-slide-5", "asset_type": "cardnews_background", "label": "IG 슬라이드 5"},
]

FALLBACK_ORDERS = {
    "gpt-image-2": ["local-bonsai", "minimax"],
    "local-bonsai": ["gpt-image-2", "minimax"],
    "minimax": ["gpt-image-2", "local-bonsai"],
}

PROFILE_CONFIGS = {
    "default": {
        "description": "품질/스타일 일관성 우선. 모든 슬롯 gpt-image-2 primary.",
        "default_model": "gpt-image-2",
        "slot_models": {},
    },
    "hybrid": {
        "description": "속도 실험용 균형 프로필. Threads 4컷만 Local Bonsai primary, 나머지는 gpt-image-2.",
        "default_model": "gpt-image-2",
        "slot_models": {
            "threads-comic": "local-bonsai",
        },
    },
    "experimental": {
        "description": "채널별 모델 분리 실험. 스타일 검수 필수.",
        "default_model": "gpt-image-2",
        "slot_models": {
            "cover": "local-bonsai",
            "body-1": "local-bonsai",
            "body-2": "local-bonsai",
            "threads-comic": "gpt-image-2",
            "ig-slide-1": "minimax",
            "ig-slide-2": "minimax",
            "ig-slide-3": "minimax",
            "ig-slide-4": "minimax",
            "ig-slide-5": "minimax",
        },
    },
}


def now_kst() -> str:
    return datetime.now(KST).isoformat(timespec="seconds")


def chunk(items: list, n: int) -> list[list]:
    return [items[i : i + n] for i in range(0, len(items), n)]


def model_for_slot(item: dict[str, Any], profile: dict[str, Any], preferred_model: str | None) -> str:
    """명시 모델 > 플랜 지정 모델 > 프로필 슬롯 모델 > 프로필 기본 모델."""
    if preferred_model:
        return preferred_model
    if item.get("preferred_model"):
        return item["preferred_model"]
    slot = item["slot"]
    return profile["slot_models"].get(slot, profile["default_model"])


def fallback_for_model(model: str) -> list[str]:
    return FALLBACK_ORDERS.get(model, ["gpt-image-2", "local-bonsai", "minimax"])


def group_for_slot(slot: str) -> tuple[str, str]:
    """style_group은 전체 작업 단위, regenerate_group은 묶음 fallback 단위."""
    if slot.startswith("ig-slide-"):
        return "job", "instagram-carousel"
    if slot.startswith("body-"):
        return "job", "blog-body"
    return "job", slot


def build_batch_requests(
    plan: list,
    batch_size: int,
    profile_name: str,
    preferred_model: str | None,
) -> list[dict[str, Any]]:
    """9장(또는 N장) 요청을 batch_size 단위로 분할."""
    profile = PROFILE_CONFIGS[profile_name]
    batches = chunk(plan, batch_size)
    return [
        {
            "batch_index": idx,
            "batch_size": len(b),
            "started_at": now_kst(),
            "profile": profile_name,
            "profile_description": profile["description"],
            "style_consistency_required": True,
            "style_scope": "entire_blog_sns_job",
            "items": [
                {
                    "slot": item["slot"],
                    "asset_type": item["asset_type"],
                    "label": item["label"],
                    "preferred_model": model_for_slot(item, profile, preferred_model),
                    "fallback_order": fallback_for_model(model_for_slot(item, profile, preferred_model)),
                    "aspect_ratio": "1:1",  # v3: 1:1 통일
                    "size": "1024x1024",
                    "style_group": group_for_slot(item["slot"])[0],
                    "regenerate_group": group_for_slot(item["slot"])[1],
                    "regenerate_group_policy": "same_model_for_group_on_fallback"
                    if item["slot"].startswith("ig-slide-")
                    else "slot_level_fallback_allowed",
                }
                for item in b
            ],
        }
        for idx, b in enumerate(batches, start=1)
    ]


def dispatch_batch(batch: dict[str, Any], out_dir: Path) -> Path:
    """각 배치를 imagemaker 서브에이전트 요청 JSON + MD로 변환. 실제 호출은 별도 단계."""
    out_dir.mkdir(parents=True, exist_ok=True)
    fname = f"batch-{batch['batch_index']:02d}.json"
    fpath = out_dir / fname
    fpath.write_text(json.dumps(batch, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return fpath


def main() -> int:
    parser = argparse.ArgumentParser(description="v3 이미지 병렬 생성 dispatcher (안전 모드: 3+3+3)")
    parser.add_argument(
        "--profile",
        choices=sorted(PROFILE_CONFIGS),
        default="default",
        help="이미지 생성 전략 프로필 (기본 default)",
    )
    parser.add_argument(
        "--preferred-model",
        default=None,
        help="모든 슬롯에 강제 적용할 선호 모델. 지정하지 않으면 profile별 모델 사용",
    )
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE, help=f"동시 호출 수 (기본 {DEFAULT_BATCH_SIZE})")
    parser.add_argument("--out-dir", type=Path, default=Path("data/imagemaker-requests/v3"))
    parser.add_argument("--plan-json", type=Path, default=None, help="커스텀 플랜 JSON (없으면 기본 9장)")
    args = parser.parse_args()

    plan = DEFAULT_9_PLAN
    if args.plan_json:
        plan = json.loads(args.plan_json.read_text(encoding="utf-8"))

    if args.batch_size < 1 or args.batch_size > 9:
        print(f"[ERROR] batch_size는 1~9 사이여야 합니다: {args.batch_size}")
        return 1

    batches = build_batch_requests(plan, args.batch_size, args.profile, args.preferred_model)
    out_dir: Path = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"# v3 이미지 병렬 생성 dispatcher")
    print(f"plan: {len(plan)}장 / batch_size: {args.batch_size} / 총 배치: {len(batches)}")
    print(f"profile: {args.profile} — {PROFILE_CONFIGS[args.profile]['description']}")
    if args.preferred_model:
        print(f"preferred_model override: {args.preferred_model}")
    print(f"out_dir: {out_dir}")
    print()
    for batch in batches:
        fpath = dispatch_batch(batch, out_dir)
        print(f"  Batch {batch['batch_index']}/{len(batches)} — {batch['batch_size']}장 → {fpath}")
        for item in batch["items"]:
            print(
                f"    - {item['slot']:18s} {item['asset_type']:30s} "
                f"{item['label']} / {item['preferred_model']} "
                f"/ fallback: {' > '.join(item['fallback_order'])}"
            )

    # 실행 로그
    log_path = Path("data/parallel_image_runs.jsonl")
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as f:
        f.write(
            json.dumps(
                {
                    "timestamp": now_kst(),
                    "event": "plan_built",
                    "plan_count": len(plan),
                    "batch_size": args.batch_size,
                    "batch_count": len(batches),
                    "profile": args.profile,
                    "preferred_model_override": args.preferred_model,
                    "out_dir": str(out_dir),
                },
                ensure_ascii=False,
            )
            + "\n"
        )

    print()
    print("✅ v3 dispatcher 준비 완료. 이제 각 배치를 imagemaker 서브에이전트에 동시 호출하면 됩니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
