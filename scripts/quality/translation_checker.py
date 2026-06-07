#!/usr/bin/env python3
"""Deterministic translation-quality checker for blog posts.

This module is the Stage-1 (auto) part of the quality pipeline described in
``agents/blogger/AGENT.md`` (Minimax + humanize-korean + Claude + GPT fallback
policy). It does NOT call any LLM — every measurement is a deterministic
regex/heuristic so the score is reproducible and CI-friendly.

Inputs
------
- ``--post``            path to a Hugo/Markdown blog post
- ``--source-url``      optional source article URL; enables fact-grounding
- ``--min-score``       override default pass threshold (70)
- ``--json``            machine-readable output (otherwise human report)

Output (always, even on FAIL)
-----------------------------
``dict`` with the following keys:
    score           : int 0..100 (100 is perfect)
    pass            : bool (``score >= min_score``)
    issues          : list[str]   (every deduction, human-readable)
    suggestions     : list[str]   (concrete fixes a writer/agent can apply)
    metrics         : dict        (raw counts, ratios used in scoring)
    threshold       : int         (the cut-off used)

The CLI prints a compact summary and exits with code 0 on PASS, 1 on FAIL.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Iterable


# ---------------------------------------------------------------------------
# Tunable constants
# ---------------------------------------------------------------------------

DEFAULT_MIN_SCORE = 70

# Common Korean AI/translation-tell patterns. Each pattern is a regex; weights
# reflect how strongly we penalise per match. These are heuristic — see the
# README "False positive" section for the rationale.
KR_TRANSLATION_TELLS: list[tuple[str, int, str]] = [
    # 직역투 / overly-formal "X는 Y이다" cadence
    (r"\b이는\s+[가-힣]{2,30}이다\b", 3, "직역투 '이는 …이다'"),
    (r"\b이러한\s+[가-힣]{2,30}은\b", 3, "직역투 '이러한 …은'"),
    (r"\b이러한\s+[가-힣]{2,30}가\b", 3, "직역투 '이러한 …가'"),
    (r"\b다음과\s+같은\b", 2, "직역투 '다음과 같은'"),
    (r"\b위와\s+같은\b", 2, "직역투 '위와 같은'"),
    (r"\b아래와\s+같은\b", 2, "직역투 '아래와 같은'"),
    # 회피 / 무의미한 연결 표현
    (r"\b[가-힣]{2,15}로\s+알려져\s+있다\b", 4, "회피 표현 '~로 알려져 있다'"),
    (r"\b[가-힣]{2,15}라\s+할\s+수\s+있다\b", 4, "회피 표현 '~라 할 수 있다'"),
    (r"\b[가-힣]{2,15}라고\s+할\s+수\s+있다\b", 4, "회피 표현 '~라고 할 수 있다'"),
    (r"\b[가-힣]{2,15}라고\s+생각된다\b", 3, "회피 표현 '~라고 생각된다'"),
    (r"\b[가-힣]{2,15}것으로\s+판단된다\b", 3, "회피 표현 '~것으로 판단된다'"),
    (r"\b[가-힣]{2,15}것으로\s+나타났다\b", 3, "회피 표현 '~것으로 나타났다'"),
    # 빈번한 접속사 반복
    (r"\b또한\b", 2, "접속사 '또한'"),
    (r"\b그리고\b", 1, "접속사 '그리고'"),
    (r"\b그러나\b", 1, "접속사 '그러나'"),
    (r"\b따라서\b", 1, "접속사 '따라서'"),
    (r"\b즉,\s", 2, "접속사 '즉,'"),
    # 1인칭 단수 (브랜드 톤 비호환)
    (r"\b저는\b", 3, "1인칭 '저는'"),
    (r"\b제가\b", 3, "1인칭 '제가'"),
    (r"\b저의\b", 3, "1인칭 '저의'"),
]

# English -> Korean translation tells. We accept either Korean or English
# body — but the Korean version is what we publish, so English-tells here
# would indicate the writer forgot to translate (e.g. left a quote verbatim).
EN_UNTRANSLATED_BLOCKLIST: list[tuple[str, int, str]] = [
    (r"\bThe following\b", 5, "영문 잔존 'The following'"),
    (r"\bIn this (article|post|guide)\b", 5, "영문 잔존 'In this article/post'"),
    (r"\bAs mentioned above\b", 5, "영문 잔존 'As mentioned above'"),
    (r"\bIt is worth noting\b", 5, "영문 잔존 'It is worth noting'"),
    (r"\bIn conclusion\b", 3, "영문 잔존 'In conclusion'"),
    (r"\bFirst and foremost\b", 4, "영문 잔존 'First and foremost'"),
]

# "구체적 수치" — we look for "₩", "$", percent signs, "만", "억" etc. and
# require either a source URL match or a citation in the post.
NUMERIC_PATTERN = re.compile(
    r"(\$[\d,\.]+[BMK]?|\₩[\d,\.]+|[±\+\-]?\d+(?:\.\d+)?\s?%|[0-9]{1,3}(?:,[0-9]{3})+|[0-9]+(?:억|만|조|명|개|대|건))"
)

# Source-side scraping: cheap & best-effort. We do NOT require network — if
# the source cannot be fetched we just skip fact-grounding.
NUMERIC_IN_SOURCE_RE = re.compile(
    r"(\$[\d,\.]+[BMK]?|[0-9]{1,3}(?:,[0-9]{3})+|[0-9]+(?:억|만|조))"
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _strip_frontmatter(text: str) -> str:
    """Drop Hugo frontmatter (between ``---`` fences) and any HTML comments."""
    text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)
    m = re.match(r"\A---\s*\n.*?\n---\s*\n", text, flags=re.DOTALL)
    if m:
        text = text[m.end():]
    return text


def _sentences(text: str) -> list[str]:
    """Cheap Korean/English sentence splitter. Good enough for ratios.

    We only split on *terminating* punctuation: a period/question/exclamation
    mark, or a clear paragraph break. Splitting on bare Korean "다" is
    tempting (it ends a polite declarative) but is wrong when it appears in
    the middle of a long sentence (e.g. "...것이다. ...") and causes
    mid-sentence splits that break the length distribution check.
    """
    text = re.sub(r"\s+", " ", text)
    # First split on paragraph break
    chunks: list[str] = []
    for para in text.split("\n"):
        para = para.strip()
        if not para:
            continue
        # Then split on Latin terminators only — these are unambiguous.
        chunks.extend(re.split(r"(?<=[.!?])\s+", para))
    return [p.strip() for p in chunks if p.strip()]


def _char_len(sent: str) -> int:
    """Count visible characters (no whitespace)."""
    return len(re.sub(r"\s", "", sent))


def _word_tokens(body: str) -> list[str]:
    """Tokenize body into lower-cased content words for repetition checks.

    Strips punctuation; keeps both Hangul and Latin words. Numbers are kept
    verbatim because they are content-significant.
    """
    body = re.sub(r"[`\*_#>~]", " ", body)
    tokens = re.findall(r"[A-Za-z0-9]+|[가-힣]{2,}", body)
    return [t.lower() for t in tokens]


def _first_sentence_of(paragraph: str) -> str:
    sents = _sentences(paragraph)
    return sents[0] if sents else ""


def _is_topic_first_sentence(sent: str) -> bool:
    """Heuristic: a 'good' first sentence has 12..120 chars and isn't a pure
    transition. Very short or very long first lines usually indicate an
    introduction that has drifted away from the section topic.
    """
    n = _char_len(sent)
    if n < 8:
        return False
    if n > 140:
        return False
    return True


def _fetch_source_text(url: str, *, timeout: float = 4.0) -> str | None:
    """Best-effort fetch. We keep this dependency-free — it uses urllib only.

    Returns the response body, or None on any failure (network/timeout/etc.).
    This is intentionally permissive: a missing source never blocks scoring;
    it just disables fact-grounding.
    """
    if not url or not url.startswith(("http://", "https://")):
        return None
    try:
        from urllib.request import Request, urlopen

        req = Request(url, headers={"User-Agent": "track-b-quality/1.0"})
        with urlopen(req, timeout=timeout) as resp:  # noqa: S310 - we control URL
            return resp.read().decode("utf-8", errors="replace")
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Measurement
# ---------------------------------------------------------------------------


def _measure_translation_tells(body: str) -> tuple[int, list[dict[str, Any]]]:
    """Return (deduction, raw hits)."""
    deduction = 0
    hits: list[dict[str, Any]] = []
    for pattern, weight, label in KR_TRANSLATION_TELLS:
        count = len(re.findall(pattern, body))
        if count:
            hits.append({"label": label, "count": count, "weight": weight})
            # Capped per-pattern: first 3 are charged at full weight, after
            # that we cap to avoid a 100-page post being crippled by a single
            # overused word.
            charge = min(count, 4) * weight
            deduction += charge
    for pattern, weight, label in EN_UNTRANSLATED_BLOCKLIST:
        count = len(re.findall(pattern, body, flags=re.IGNORECASE))
        if count:
            hits.append({"label": label, "count": count, "weight": weight})
            deduction += min(count, 3) * weight
    return deduction, hits


def _measure_repetition(tokens: list[str], body_chars: int) -> tuple[int, list[dict[str, Any]]]:
    """Charge for words appearing too often, normalised by body length.

    Spec: "본문 1000자당 동일 단어 5회 이상 등장 시 경고". A word is only
    a candidate if it appears at least 5 times AND its density is > 5 per
    1000 chars. The dual condition prevents one-occurrence words in
    short bodies from being penalised (a single "안녕하세요" in a 19-char
    greeting body is dense, but it doesn't repeat).

    Each charged word deducts at most 10 points; proper nouns and topic-
    defining acronyms are charged at half weight because a real blog post
    will mention SpaceX / Google / AI / IPO dozens of times.
    """
    if not tokens or body_chars <= 0:
        return 0, []
    counter = Counter(tokens)
    char_per_k = body_chars / 1000.0
    deduction = 0
    hits: list[dict[str, Any]] = []
    for word, count in counter.most_common(30):
        if len(word) < 2:
            continue
        if count < 5:
            # Single-occurrence words in short bodies would otherwise
            # look "dense"; require 5+ repetitions.
            continue
        per_k = count / char_per_k
        if per_k < 5:
            continue
        # Proper noun? Tokens like "spacex", "google", "ai", "ipo",
        # "nvidia" are content-defining acronyms; they will (and should)
        # repeat a lot. We only charge them at half weight.
        is_acronym = (word.isascii() and word.isalpha() and word.islower() and len(word) <= 6)
        is_proper = (
            (word[:1].isupper() and word[1:].islower()) or word.isupper() or is_acronym
        )
        # Capped penalty: (per_k - 4) * 2, max 10 per word.
        penalty = min(int((per_k - 4) * 2), 10)
        if is_proper:
            penalty = max(1, penalty // 2)
        if penalty <= 0:
            continue
        deduction += penalty
        hits.append({"word": word, "count": count, "per_k": round(per_k, 1), "penalty": penalty, "is_proper": is_proper})
    return deduction, hits


def _measure_sentence_lengths(body: str) -> tuple[int, dict[str, Any], list[str]]:
    """Penalise runs of extremely short or extremely long sentences.

    Targets a readable rhythm: 18..200 visible chars per sentence. The
    lower bound is intentionally low (a 5-7 word declarative in Korean
    can be 20-30 chars); the upper bound is generous to allow a single
    long sentence for emphasis.
    """
    sents = _sentences(body)
    if not sents:
        return 0, {"total": 0}, []
    lengths = [_char_len(s) for s in sents]
    too_short = sum(1 for n in lengths if n < 18)
    too_long = sum(1 for n in lengths if n > 200)
    deduction = 0
    issues: list[str] = []
    total = len(sents)
    short_ratio = too_short / total
    long_ratio = too_long / total
    if short_ratio > 0.5:
        penalty = int(15 * short_ratio)
        deduction += penalty
        issues.append(f"너무 짧은 문장 비율 {short_ratio:.0%} (>{50}%)")
    if long_ratio > 0.25:
        penalty = int(15 * long_ratio)
        deduction += penalty
        issues.append(f"호흡이 긴 문장 비율 {long_ratio:.0%} (>{25}%)")
    return deduction, {"total": total, "short": too_short, "long": too_long}, issues


def _measure_paragraphs(body: str) -> tuple[int, list[str], list[str]]:
    """Penalise 5+ line paragraphs and 'off-topic' intros per paragraph."""
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", body) if p.strip()]
    deduction = 0
    issues: list[str] = []
    suggestions: list[str] = []
    long_paragraphs = 0
    for p in paragraphs:
        line_count = len(p.splitlines())
        if line_count >= 5:
            long_paragraphs += 1
    if long_paragraphs:
        penalty = 3 * long_paragraphs
        deduction += penalty
        issues.append(f"5줄 이상 단락 {long_paragraphs}개 (가독성 저하)")
        suggestions.append("긴 단락을 3줄 이하로 쪼개세요. 핵심 문장만 남기고 나머지는 다음 단락으로.")
    bad_intros = 0
    for p in paragraphs:
        first = _first_sentence_of(p)
        if not first:
            continue
        if not _is_topic_first_sentence(first):
            bad_intros += 1
    if bad_intros and bad_intros >= max(1, len(paragraphs) // 3):
        penalty = 4 * bad_intros
        deduction += penalty
        issues.append(f"주제에서 벗어난 도입 {bad_intros}개 단락")
        suggestions.append("각 단락 첫 줄이 그 단락의 핵심 주제를 담는지 점검하세요.")
    return deduction, issues, suggestions


def _measure_facts(
    body: str, source_url: str
) -> tuple[int, list[str], list[str]]:
    """Heuristic fact-grounding: each numeric figure in the post is checked
    against the source. Missing source disables the check (no penalty).
    """
    if not source_url:
        return 0, ["원문 URL 미제공으로 사실관계 검사 생략"], []
    src_text = _fetch_source_text(source_url)
    if src_text is None:
        return 0, ["원문 URL fetch 실패 (네트워크/timeout) — 사실관계 검사 생략"], []
    body_nums = set(NUMERIC_IN_SOURCE_RE.findall(body))
    if not body_nums:
        return 0, [], []
    src_nums = set(NUMERIC_IN_SOURCE_RE.findall(src_text))
    ungrounded: list[str] = []
    for n in body_nums:
        if n not in src_nums:
            ungrounded.append(n)
    if not ungrounded:
        return 0, [], []
    penalty = min(15, 3 * len(ungrounded))
    issues = [
        f"출처에 없는 구체적 수치 {len(ungrounded)}개 (예: {', '.join(ungrounded[:3])})"
    ]
    suggestions = [
        "원문에 없는 수치는 출처를 추가하거나 일반 표현으로 바꾸세요.",
    ]
    return penalty, issues, suggestions


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def check_translation(
    post_path: str | Path,
    source_url: str | None = None,
    min_score: int = DEFAULT_MIN_SCORE,
) -> dict[str, Any]:
    """Score a blog post. See module docstring for return shape."""
    path = Path(post_path).expanduser()
    if not path.exists():
        return {
            "score": 0,
            "pass": False,
            "issues": [f"post file missing: {path}"],
            "suggestions": ["--post 경로가 실제 .md 파일인지 확인하세요."],
            "metrics": {},
            "threshold": min_score,
        }

    raw = path.read_text(encoding="utf-8", errors="replace")
    body = _strip_frontmatter(raw).strip()
    if not body:
        return {
            "score": 0,
            "pass": False,
            "issues": ["post body is empty"],
            "suggestions": ["frontmatter만 있고 본문이 비어 있습니다."],
            "metrics": {},
            "threshold": min_score,
        }

    tokens = _word_tokens(body)
    char_count = _char_len(body)

    tell_deduction, tell_hits = _measure_translation_tells(body)
    rep_deduction, rep_hits = _measure_repetition(tokens, char_count)
    len_deduction, len_metrics, len_issues = _measure_sentence_lengths(body)
    para_deduction, para_issues, para_suggestions = _measure_paragraphs(body)
    fact_deduction, fact_issues, fact_suggestions = _measure_facts(body, source_url or "")

    deduction = tell_deduction + rep_deduction + len_deduction + para_deduction + fact_deduction
    score = max(0, 100 - deduction)

    issues: list[str] = []
    issues.extend(f"{h['label']} {h['count']}회" for h in tell_hits)
    issues.extend(f"단어 '{h['word']}' {h['count']}회 반복" for h in rep_hits)
    issues.extend(len_issues)
    issues.extend(para_issues)
    issues.extend(fact_issues)

    suggestions: list[str] = []
    if tell_hits:
        suggestions.append(
            "직역투/회피 표현을 의미가 같은 자연스러운 한국어로 다시 씁니다. "
            "'Skill tool → openclaw-skills:humanize-korean'로 자동 윤문하세요."
        )
    if rep_hits:
        suggestions.append(
            "반복 단어는 대명사/구체 명사/약어로 교체하거나, 두 개 이상 등장하면 "
            "그중 하나를 다른 단어로 바꿉니다."
        )
    if len_issues:
        suggestions.append("문장 호흡이 한쪽으로 쏠려 있습니다. 짧고 긴 문장을 번갈아 배치하세요.")
    suggestions.extend(para_suggestions)
    suggestions.extend(fact_suggestions)

    metrics = {
        "char_count": char_count,
        "token_count": len(tokens),
        "translation_tell_hits": tell_hits,
        "repetition_hits": rep_hits,
        "sentence_metrics": len_metrics,
        "deduction_breakdown": {
            "translation_tells": tell_deduction,
            "repetition": rep_deduction,
            "sentence_lengths": len_deduction,
            "paragraphs": para_deduction,
            "facts": fact_deduction,
            "total": deduction,
        },
    }

    return {
        "score": score,
        "pass": score >= min_score,
        "issues": issues,
        "suggestions": suggestions,
        "metrics": metrics,
        "threshold": min_score,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _format_report(result: dict[str, Any], *, verbose: bool = True) -> str:
    lines: list[str] = []
    score = result.get("score", 0)
    passed = result.get("pass", False)
    status = "PASS" if passed else "FAIL"
    lines.append(f"[{status}] translation score: {score}/100  (threshold {result.get('threshold')})")
    issues = result.get("issues") or []
    if issues:
        lines.append("Issues:")
        for i in issues:
            lines.append(f"  - {i}")
    suggestions = result.get("suggestions") or []
    if suggestions and verbose:
        lines.append("Suggestions:")
        for s in suggestions:
            lines.append(f"  - {s}")
    metrics = result.get("metrics") or {}
    breakdown = metrics.get("deduction_breakdown") or {}
    if verbose and breakdown:
        lines.append(
            "Deduction breakdown: "
            + ", ".join(f"{k}={v}" for k, v in breakdown.items() if k != "total")
            + f"  (total {breakdown.get('total', 0)})"
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Deterministic blog-post translation quality scorer"
    )
    parser.add_argument("--post", required=True, help="path to .md blog post")
    parser.add_argument("--source-url", default="", help="optional source article URL")
    parser.add_argument("--min-score", type=int, default=DEFAULT_MIN_SCORE)
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args(argv)

    result = check_translation(args.post, args.source_url or None, args.min_score)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(_format_report(result))
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
