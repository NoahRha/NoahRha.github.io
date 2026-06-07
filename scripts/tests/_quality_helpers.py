"""Shared test helpers for the Track-B quality checker unit tests.

We do not use ``conftest.py`` (Track C owns that file) or the global
``_helpers.py`` (also owned by Track C). The Track-B tests share their
helpers through this module instead.
"""

from __future__ import annotations

import io
import sys
from pathlib import Path

import pytest
from PIL import Image


def make_png(
    path: Path,
    *,
    size: tuple[int, int] = (1024, 1024),
    color: tuple[int, int, int] = (200, 100, 50),
    mode: str = "RGB",
) -> Path:
    """Write a small valid PNG. The default ``size`` is the spec target
    (1024x1024) but most tests build at 10x10 then resize; the
    resize-then-save approach is what produces accurate dimensions in
    the file header."""
    im = Image.new(mode, (10, 10), color)
    path.parent.mkdir(parents=True, exist_ok=True)
    if size != (10, 10):
        im = im.resize(size)
    im.save(path, format="PNG", optimize=True)
    return path


def write_text(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def tiny_post_body() -> str:
    """Short, intentionally AI-tell-heavy Korean paragraph (< 70 score)."""
    return (
        "이는 SpaceX의 새로운 계약에 관한 글이다. 이러한 계약은 매우 중요하다. "
        "이러한 흐름은 업계 전반에 큰 영향을 미친다. 이러한 변화는 AI 시장에 "
        "새로운 전환점이 될 것이다. 다음과 같은 이유로 업계의 관심이 크다. "
        "위와 같은 이유로 시장은 빠르게 움직이고 있다. 아래와 같은 관점에서 "
        "보면 이번 계약은 회사의 미래를 결정짓는다고 할 수 있다. "
        "그리고 동시에 Google과의 계약도 잘 알려져 있다. 그리고 Microsoft와의 "
        "협력도 잘 알려져 있다. 따라서 이번 계약은 매우 중요하다고 할 수 있다. "
        "따라서 업계는 이 변화를 주목하고 있다. 따라서 투자자들의 시선이 집중된다. "
        "또한 이는 단순한 GPU 임대가 아니라 새로운 인프라 사업으로 볼 수 있다. "
        "또한 AI 업계 전반에 큰 영향을 미칠 것이라고 할 수 있다. "
        "또한 데이터센터 사업자에게도 새로운 기회가 될 것이라고 할 수 있다. "
        "저는 이 소식을 전하면서 독자 여러분께 깊이 있는 분석을 드리고자 합니다. "
        "제 경험상 AI 인프라 시장은 빠르게 성장하고 있습니다. "
        "저의 분석에 따르면 GPU 확보는 곧 경쟁력 확보라고 할 수 있습니다. "
        "이는 명확한 사실이다. 위의 내용을 정리하면 다음과 같다. "
        "100억 달러 규모의 계약이 체결되었다고 할 수 있다. "
        "1만 1000개의 칩이 임대된다고 할 수 있다. 2026년 10월부터 시작된다. "
        "2029년 6월까지 지속된다. 이는 매우 큰 규모라고 할 수 있다."
    )


def clean_post_body() -> str:
    """A natural Korean post body with no obvious AI tells."""
    return (
        "SpaceX가 Google에 대규모 AI 칩 접근권을 제공하는 계약을 맺었다는 "
        "보도가 나왔습니다. 숫자만 봐도 큽니다. 월 9.2억 달러, 기간은 "
        "2026년 10월부터 2029년 6월까지, Google이 접근하는 Nvidia AI 칩은 "
        "약 11만 개입니다.\n\n"
        "이 뉴스가 흥미로운 이유는 단순히 \"Google이 GPU를 빌렸다\"가 "
        "아니기 때문입니다. IPO를 앞둔 SpaceX가 우주 발사·위성 인터넷 "
        "기업을 넘어, 남는 AI 컴퓨팅 용량을 외부에 빌려주는 인프라 사업자로 "
        "읽히기 시작했다는 점이 핵심입니다.\n\n"
        "이번 SpaceX와 Google 계약 보도는 AI 산업의 무게중심이 어디로 "
        "이동하는지 잘 보여줍니다. AI 서비스가 커질수록 가장 귀한 것은 "
        "멋진 데모만이 아닙니다. 고객이 실제로 몰리는 순간에도 버틸 수 있는 "
        "칩, 전력, 데이터센터, 그리고 그 용량을 확보하는 계약입니다."
    )


@pytest.fixture
def tmp_image_dir(tmp_path: Path) -> Path:
    d = tmp_path / "images"
    d.mkdir()
    return d
