#!/usr/bin/env python3
"""Korean translation naturalness gate for blog drafts.

This lightweight checker catches two classes of issues that often make
English-to-Korean blog translations read like raw AI output:

1. Foreign CJK remnants such as Chinese/Japanese characters left in Korean text.
2. Repeated formulaic endings such as "시사합니다" or "할 것입니다".

It is intentionally conservative. It does not rewrite text; it only reports
whether the draft should go through a humanize-korean pass before publishing.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


FOREIGN_CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\u3040-\u30ff]")
AI_TRANSLATION_PATTERNS = [
    ("시사합니다", re.compile(r"시사(?:합니다|한다|했다|하고 있습니다|하고 있다)")),
    ("전망입니다", re.compile(r"전망(?:입니다|이다|됩니다|된다|했습니다|했다)")),
    ("할 것입니다", re.compile(r"(?:할|될|이어질|확대될|가속화될)\s*것(?:입니다|이다)")),
    ("가능성이 있습니다", re.compile(r"가능성이\s*(?:있습니다|있다|큽니다|크다)")),
    ("보여줍니다/의미합니다", re.compile(r"보여(?:줍니다|준다)|의미(?:합니다|한다)")),
]
MIXED_ENGLISH_RE = re.compile(
    r"\b(?:production-ready|Robust|Inclusive|capability|fundraising|business model|milestone)\b",
    re.IGNORECASE,
)


def line_number(text: str, index: int) -> int:
    return text.count("\n", 0, index) + 1


def strip_frontmatter(text: str) -> str:
    return re.sub(r"^---.*?---\s*", "", text, flags=re.DOTALL).strip()


def check_translation_naturalness(text: str) -> dict:
    body = strip_frontmatter(text)

    foreign_hits = [
        {"char": match.group(0), "line": line_number(body, match.start())}
        for match in list(FOREIGN_CJK_RE.finditer(body))[:10]
    ]

    ai_hits = []
    total_ai_pattern_hits = 0
    for label, pattern in AI_TRANSLATION_PATTERNS:
        matches = list(pattern.finditer(body))
        if matches:
            total_ai_pattern_hits += len(matches)
            ai_hits.append(
                {
                    "pattern": label,
                    "count": len(matches),
                    "lines": [line_number(body, m.start()) for m in matches[:5]],
                }
            )

    mixed_english_hits = [
        {"term": match.group(0), "line": line_number(body, match.start())}
        for match in list(MIXED_ENGLISH_RE.finditer(body))[:10]
    ]

    ai_pattern_fail = total_ai_pattern_hits >= 3 or any(hit["count"] >= 2 for hit in ai_hits)
    mixed_english_warning = len(mixed_english_hits) >= 3

    return {
        "passed": not foreign_hits and not ai_pattern_fail,
        "foreign_cjk_count": len(foreign_hits),
        "foreign_cjk_hits": foreign_hits,
        "ai_translation_pattern_count": total_ai_pattern_hits,
        "ai_translation_hits": ai_hits,
        "mixed_english_warning": mixed_english_warning,
        "mixed_english_hits": mixed_english_hits,
        "recommendation": "run_humanize_korean" if foreign_hits or ai_pattern_fail or mixed_english_warning else "ok",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Korean blog translation naturalness gate")
    parser.add_argument("post", type=Path, help="Markdown post or draft")
    args = parser.parse_args()

    result = check_translation_naturalness(args.post.read_text(encoding="utf-8"))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
