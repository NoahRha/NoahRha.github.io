#!/usr/bin/env python3
"""Deterministic image-quality checker for blog/SNS asset folders.

Stage-1 of the quality pipeline. All measurements are deterministic so the
score is reproducible. We use only the Python standard library + Pillow
(``PIL``); no LLM, no network, no external API.

The checker audits a directory of image files (typically
``static/images/<slug>/``) for:
  1. File integrity: PNG/JPG magic bytes, zero-byte, truncation.
  2. Metadata: SHA-256 dedup, file-size placeholder detection.
  3. Visual diversity (mean RGB cosine similarity) — uses only PIL.
  4. Style consistency: every asset's ``style`` field matches the
     requested style (hand-drawing vs oil); prompt style-prefix present.
  5. Aspect ratio: 1:1, 1024..1080 px on each side (Hugo/SNS spec).

Score: 100 minus deductions. Below 80 → FAIL.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import struct
import sys
from collections import Counter
from pathlib import Path
from typing import Any

try:
    from PIL import Image, UnidentifiedImageError
except Exception as exc:  # pragma: no cover - PIL is required
    print(f"[ERROR] PIL is required for image_checker: {exc}", file=sys.stderr)
    raise

# ---------------------------------------------------------------------------
# Tunable constants
# ---------------------------------------------------------------------------

DEFAULT_MIN_SCORE = 80
DEFAULT_STYLE = "hand-drawing"
STYLE_PREFIXES = {
    "hand-drawing": ("hand-drawn", "ink", "pen", "cross-hatch", "drawing", "linework"),
    "oil": ("oil painting", "oil-painting", "painterly", "brushstroke", "oil on canvas"),
}
ALLOWED_EXT = {".png", ".jpg", ".jpeg", ".webp"}
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
JPG_MAGIC = b"\xff\xd8\xff"
WEBP_MAGIC = b"RIFF"
MIN_BYTES = 5 * 1024        # < 5KB ⇒ suspicious placeholder
EXPECTED_RATIO = 1.0        # 1:1
RATIO_TOLERANCE = 0.05      # ±5%
# Square side is the spec target (1024 source) but cards render at 1080 too
ALLOWED_SIDES = {(1024, 1024), (1080, 1080)}
# Allow ±5% drift on each side
SIDE_TOLERANCE = 0.05


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _read_magic(path: Path, n: int = 16) -> bytes:
    with path.open("rb") as fh:
        return fh.read(n)


def _sha256(path: Path, chunk: int = 65536) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            buf = fh.read(chunk)
            if not buf:
                break
            h.update(buf)
    return h.hexdigest()


def _is_png(buf: bytes) -> bool:
    return buf.startswith(PNG_MAGIC)


def _is_jpg(buf: bytes) -> bool:
    return buf.startswith(JPG_MAGIC)


def _is_webp(buf: bytes) -> bool:
    # RIFF at offset 0; 'WEBP' fourCC at offset 8
    return len(buf) >= 12 and buf.startswith(WEBP_MAGIC) and buf[8:12] == b"WEBP"


def _is_truncated(path: Path) -> bool:
    """A truncated image: PIL can decode the header but reading pixels fails
    OR the IEND marker is missing for PNG.
    """
    try:
        with Image.open(path) as im:
            im.load()
            im.getpixel((0, 0))
    except (UnidentifiedImageError, OSError, ValueError, struct.error):
        return True
    # Check PNG IEND marker (last 8 bytes should contain it)
    if path.suffix.lower() == ".png":
        with path.open("rb") as fh:
            fh.seek(-12, 2)
            tail = fh.read(12)
        if b"IEND" not in tail:
            return True
    return False


def _mean_rgb(path: Path) -> tuple[int, int, int] | None:
    """Compute mean (R,G,B) for a small thumbnail. Robust to alpha/transparency.
    Returns None if the file cannot be decoded.

    We use ``tobytes()`` rather than ``getdata()`` to avoid Pillow's
    deprecation warning (``getdata`` is slated for removal in Pillow 14).
    """
    try:
        with Image.open(path) as im:
            im.thumbnail((128, 128))
            if im.mode != "RGB":
                im = im.convert("RGB")
            raw = im.tobytes()
            n_pixels = im.size[0] * im.size[1]
            if n_pixels == 0:
                return None
            r = sum(raw[0::3]) // n_pixels
            g = sum(raw[1::3]) // n_pixels
            b = sum(raw[2::3]) // n_pixels
            return (r, g, b)
    except (UnidentifiedImageError, OSError, ValueError):
        return None


def _color_distance(c1: tuple[int, int, int], c2: tuple[int, int, int]) -> float:
    """Euclidean RGB distance. We use this instead of cosine for raw RGB
    vectors because the magnitude carries saturation/lightness information
    that the editorial review cares about.
    """
    return math.sqrt(sum((a - b) ** 2 for a, b in zip(c1, c2)))


def _is_placeholder_color(rgb: tuple[int, int, int] | None) -> bool:
    """Near-pure black or near-pure white = suspicious (image was not drawn)."""
    if rgb is None:
        return True
    r, g, b = rgb
    if max(r, g, b) - min(r, g, b) > 12:
        return False  # not monochrome
    return r < 8 or r > 247


def _parse_dimensions_png(path: Path) -> tuple[int, int] | None:
    """Read PNG width/height from the IHDR chunk (bytes 16..24)."""
    try:
        with path.open("rb") as fh:
            data = fh.read(24)
        if not _is_png(data):
            return None
        w, h = struct.unpack(">II", data[16:24])
        return (w, h)
    except (OSError, struct.error):
        return None


def _parse_dimensions_jpg(path: Path) -> tuple[int, int] | None:
    """Scan JPEG SOFn marker. Returns (w, h) or None."""
    try:
        with path.open("rb") as fh:
            data = fh.read()
    except OSError:
        return None
    if not _is_jpg(data):
        return None
    i = 2
    while i < len(data) - 9:
        if data[i] != 0xFF:
            i += 1
            continue
        marker = data[i + 1]
        # SOF0..SOF15 except DHT (0xC0..0xCF except 0xC4)
        if marker in {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}:
            h, w = struct.unpack(">HH", data[i + 5:i + 9])
            return (w, h)
        size = struct.unpack(">H", data[i + 2:i + 4])[0]
        i += 2 + size
    return None


def _parse_dimensions_webp(path: Path) -> tuple[int, int] | None:
    """Read WebP dimensions.

    WebP layout: ``RIFF<size>WEBP<chunk><chunk-data>``. The first chunk
    FourCC is at offset 12; ``VP8 `` (lossy) puts width/height at bytes
    26/28 of the file; ``VP8L`` (lossless) at 21..24.
    """
    try:
        with path.open("rb") as fh:
            data = fh.read(64)
    except OSError:
        return None
    if not _is_webp(data):
        return None
    # 'VP8 ' (lossy) at offset 12 → width/height at 26/28
    if data[12:16] == b"VP8 ":
        w = struct.unpack("<H", data[26:28])[0] & 0x3FFF
        h = struct.unpack("<H", data[28:30])[0] & 0x3FFF
        return (w, h)
    # 'VP8L' (lossless) at offset 12
    if data[12:16] == b"VP8L":
        b0, b1, b2, b3 = data[21], data[22], data[23], data[24]
        w = ((b1 & 0x3F) << 8 | b0) + 1
        h = (((b3 & 0x0F) << 10) | (b2 << 2) | ((b1 & 0xC0) >> 6)) + 1
        return (w, h)
    return None


def _get_dimensions(path: Path) -> tuple[int, int] | None:
    """Get pixel dimensions without loading the whole image."""
    suf = path.suffix.lower()
    if suf == ".png":
        return _parse_dimensions_png(path)
    if suf in {".jpg", ".jpeg"}:
        return _parse_dimensions_jpg(path)
    if suf == ".webp":
        return _parse_dimensions_webp(path)
    return None


def _ratio_ok(w: int, h: int) -> bool:
    if w <= 0 or h <= 0:
        return False
    ratio = w / h
    return abs(ratio - EXPECTED_RATIO) <= RATIO_TOLERANCE


def _side_ok(w: int, h: int) -> bool:
    if w != h:
        return False
    for sw, sh in ALLOWED_SIDES:
        if abs(w - sw) / sw <= SIDE_TOLERANCE and abs(h - sh) / sh <= SIDE_TOLERANCE:
            return True
    return False


def _style_prefix_present(prompt: str, style: str) -> bool:
    p = prompt.lower()
    for token in STYLE_PREFIXES.get(style, ()):
        if token in p:
            return True
    return False


def _read_image_plan(plan_path: Path) -> dict[str, Any] | None:
    if not plan_path.exists():
        return None
    try:
        return json.loads(plan_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


# ---------------------------------------------------------------------------
# Per-image audit
# ---------------------------------------------------------------------------


def _audit_one(path: Path, expected_style: str | None) -> dict[str, Any]:
    issues: list[str] = []
    suggestions: list[str] = []
    checks: dict[str, Any] = {}

    # File integrity
    size = path.stat().st_size if path.exists() else 0
    checks["size_bytes"] = size
    magic = _read_magic(path, 16) if path.exists() else b""
    # SHA-256 is computed for *every* file (even 0-byte) so the global
    # dedup pass never crashes on a missing key. 0-byte files hash to the
    # well-known SHA-256 of the empty string ("e3b0c44...") which means
    # a folder full of 0-byte files will trip the dedup rule — a feature,
    # not a bug: 5+ identical 0-byte files are clearly the same generator
    # failure repeated.
    checks["sha256"] = _sha256(path)
    if size == 0:
        issues.append("0-byte file (generation failed?)")
        return {
            "path": str(path),
            "filename": path.name,
            "score": 0,
            "issues": issues,
            "suggestions": ["regenerate"],
            "checks": checks,
        }
    if not (_is_png(magic) or _is_jpg(magic) or _is_webp(magic)):
        issues.append(f"bad magic bytes (not PNG/JPG/WEBP): {magic[:8]!r}")
    if size < MIN_BYTES:
        issues.append(f"file is only {size}B — placeholder suspected")
        suggestions.append("regenerate with non-trivial output (>5KB)")
    if _is_truncated(path):
        issues.append("image is truncated (PIL could not decode fully)")

    # Visual diversity / placeholder detection
    rgb = _mean_rgb(path)
    checks["mean_rgb"] = list(rgb) if rgb else None
    if _is_placeholder_color(rgb):
        issues.append(f"placeholder color suspected: mean RGB={rgb}")
        suggestions.append("regenerate — current image is near-monochrome (black/white)")

    # Dimensions / aspect ratio
    dims = _get_dimensions(path)
    checks["dimensions"] = list(dims) if dims else None
    if dims is None:
        issues.append("could not read pixel dimensions")
    else:
        w, h = dims
        if not _ratio_ok(w, h):
            issues.append(f"aspect ratio is {w}:{h}, must be 1:1 (±{int(RATIO_TOLERANCE*100)}%)")
        if not _side_ok(w, h):
            issues.append(f"dimensions {w}x{h} not in spec (1024±5% or 1080±5%)")

    # Style consistency check is on the prompt field; we cannot always
    # inspect the prompt from the file. Skip if no plan reference; if the
    # caller passed expected_style, we still record it for the global pass.
    checks["expected_style"] = expected_style

    # Per-image score: 100 minus 30 per hard issue, 8 per soft issue.
    # "Hard" = structural failure (won't render / won't meet spec). These
    # are the kinds of defects that downstream consumers (Hugo, SNS) will
    # reject outright, so we deduct heavily even when only one image is
    # bad. Soft issues (placeholder color, style mismatch) are warnings.
    hard_keywords = (
        "0-byte",
        "bad magic",
        "truncated",
        "could not read",
        "dimensions",
        "aspect ratio",
        "placeholder suspected: mean RGB",
    )
    hard = sum(1 for i in issues if any(k in i for k in hard_keywords))
    soft = len(issues) - hard
    score = max(0, 100 - hard * 30 - soft * 8)

    return {
        "path": str(path),
        "filename": path.name,
        "score": score,
        "issues": issues,
        "suggestions": suggestions,
        "checks": checks,
    }


# ---------------------------------------------------------------------------
# Global / folder-level audit
# ---------------------------------------------------------------------------


def check_images(
    image_dir: str | Path,
    *,
    style: str = DEFAULT_STYLE,
    image_plan_path: str | Path | None = None,
    min_score: int = DEFAULT_MIN_SCORE,
) -> dict[str, Any]:
    """Run every per-image + global check. See module docstring."""
    image_dir = Path(image_dir).expanduser()
    files = sorted(
        p for p in image_dir.iterdir() if p.is_file() and p.suffix.lower() in ALLOWED_EXT
    ) if image_dir.exists() else []

    if not files:
        return {
            "score": 0,
            "pass": False,
            "issues": [f"image dir has no PNG/JPG/WEBP files: {image_dir}"],
            "suggestions": ["run image_resume_runner.py init + record to populate the directory"],
            "per_image": [],
            "global": {"file_count": 0, "duplicates": [], "style_consistency": {}, "dimension_summary": []},
            "threshold": min_score,
        }

    per_image = [_audit_one(f, style) for f in files]

    # ---- global: dedup ----
    sha_counter: Counter[str] = Counter(p["checks"]["sha256"] for p in per_image)
    duplicates = [
        {"sha256": h, "count": c, "files": [pi["filename"] for pi in per_image if pi["checks"]["sha256"] == h]}
        for h, c in sha_counter.items()
        if c >= 5
    ]
    if duplicates:
        # 5+ images with same hash is clearly wrong
        dup_penalty = 50
    else:
        dup_penalty = 0

    # ---- global: visual diversity ----
    rgbs: list[tuple[int, int, int]] = [tuple(p["checks"]["mean_rgb"]) for p in per_image if p["checks"].get("mean_rgb")]
    diversity_penalty = 0
    diversity_note = ""
    if len(rgbs) >= 2:
        max_dist = max(_color_distance(a, b) for a in rgbs for b in rgbs)
        if max_dist < 30:
            diversity_penalty = 12
            diversity_note = f"이미지 색상이 매우 비슷 (max RGB 거리 {max_dist:.1f}/441)"
        elif max_dist < 60:
            diversity_note = f"이미지 색상이 다소 비슷 (max RGB 거리 {max_dist:.1f}/441)"

    # ---- global: aspect ratio roll-up ----
    bad_aspect = [pi["filename"] for pi in per_image if any("aspect ratio" in i for i in pi["issues"])]
    bad_side = [pi["filename"] for pi in per_image if any("dimensions" in i for i in pi["issues"])]

    # ---- global: style consistency vs image plan ----
    plan = _read_image_plan(Path(image_plan_path)) if image_plan_path else None
    style_consistency: dict[str, Any] = {"expected": style, "plan_styles": [], "prompt_prefix_missing": []}
    if plan and isinstance(plan.get("assets"), list):
        plan_styles: list[str] = []
        prefix_missing: list[str] = []
        for asset in plan["assets"]:
            asset_style = str(asset.get("style") or "")
            if asset_style:
                plan_styles.append(asset_style)
            if asset_style and asset_style != style:
                prefix_missing.append(f"asset {asset.get('id')} style={asset_style} != {style}")
            prompt = str(asset.get("prompt") or "")
            if prompt and not _style_prefix_present(prompt, asset_style or style):
                prefix_missing.append(f"asset {asset.get('id')} prompt missing style prefix for {asset_style or style}")
        style_consistency["plan_styles"] = plan_styles
        style_consistency["prompt_prefix_missing"] = prefix_missing

    # ---- aggregate score ----
    per_image_avg = sum(p["score"] for p in per_image) / len(per_image)
    deduction = (
        (100 - per_image_avg)  # all per-image issues
        + dup_penalty
        + diversity_penalty
        + (20 * len(prefix_missing) if style_consistency.get("prompt_prefix_missing") else 0)
    )
    score = max(0, int(100 - deduction))

    issues: list[str] = []
    suggestions: list[str] = []
    for pi in per_image:
        for i in pi["issues"]:
            issues.append(f"{pi['filename']}: {i}")
    for pi in per_image:
        for s in pi["suggestions"]:
            suggestions.append(f"{pi['filename']}: {s}")
    for d in duplicates:
        issues.append(
            f"중복 해시 {d['sha256'][:12]}… 이 {d['count']}개 이미지에서 발견 — 같은 이미지 재사용 의심"
        )
        suggestions.append("각 이미지가 고유한지 확인하고 중복 시 재생성하세요.")
    if diversity_penalty:
        issues.append(diversity_note)
        suggestions.append("이미지 프롬프트를 다양화 (장면/색상/구도) 하세요.")
    for m in style_consistency.get("prompt_prefix_missing", []):
        issues.append(f"스타일 일관성: {m}")
        suggestions.append("모든 image plan asset의 prompt에 style prefix (hand-drawn / oil painting)을 포함하세요.")

    return {
        "score": score,
        "pass": score >= min_score,
        "issues": issues,
        "suggestions": suggestions,
        "per_image": per_image,
        "global": {
            "file_count": len(files),
            "duplicates": duplicates,
            "diversity_note": diversity_note,
            "bad_aspect": bad_aspect,
            "bad_side": bad_side,
            "style_consistency": style_consistency,
        },
        "threshold": min_score,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _format_report(result: dict[str, Any]) -> str:
    lines: list[str] = []
    score = result.get("score", 0)
    passed = result.get("pass", False)
    status = "PASS" if passed else "FAIL"
    lines.append(f"[{status}] image score: {score}/100  (threshold {result.get('threshold')})")
    g = result.get("global") or {}
    lines.append(
        f"Global: {g.get('file_count', 0)} files, "
        f"{len(g.get('duplicates') or [])} duplicate-hash groups, "
        f"{len(g.get('bad_aspect') or [])} bad aspect, "
        f"{len(g.get('bad_side') or [])} bad dimensions, "
        f"{len((g.get('style_consistency') or {}).get('prompt_prefix_missing') or [])} style-prompt issues"
    )
    if g.get("diversity_note"):
        lines.append(f"Diversity: {g['diversity_note']}")
    issues = result.get("issues") or []
    if issues:
        lines.append("Issues:")
        for i in issues:
            lines.append(f"  - {i}")
    suggestions = result.get("suggestions") or []
    if suggestions:
        lines.append("Suggestions:")
        for s in suggestions:
            lines.append(f"  - {s}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Deterministic blog/SNS image quality scorer"
    )
    parser.add_argument("--image-dir", required=True, help="directory containing image files")
    parser.add_argument("--style", choices=sorted(STYLE_PREFIXES), default=DEFAULT_STYLE)
    parser.add_argument("--image-plan", help="optional path to image plan JSON")
    parser.add_argument("--min-score", type=int, default=DEFAULT_MIN_SCORE)
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args(argv)

    result = check_images(
        args.image_dir,
        style=args.style,
        image_plan_path=args.image_plan,
        min_score=args.min_score,
    )
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(_format_report(result))
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
