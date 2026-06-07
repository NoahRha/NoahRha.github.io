"""Unit tests for image_checker.

Covers all five measurement categories (file integrity, dedup, visual
diversity, style consistency, aspect ratio) plus the public ``check_images``
API and the CLI exit codes. We build small PNGs in tmp dirs to drive the
tests.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from PIL import Image

SCRIPTS = Path(__file__).resolve().parents[1] / "quality"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

TESTS_DIR = Path(__file__).resolve().parent
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

from image_checker import (  # noqa: E402
    DEFAULT_MIN_SCORE,
    _audit_one,
    _get_dimensions,
    _is_jpg,
    _is_png,
    _is_webp,
    _mean_rgb,
    _parse_dimensions_jpg,
    _parse_dimensions_png,
    _parse_dimensions_webp,
    _sha256,
    _style_prefix_present,
    check_images,
    main,
)

from _quality_helpers import make_png  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def write_plan(tmp_path: Path, assets: list[dict]) -> Path:
    p = tmp_path / "plan.json"
    p.write_text(json.dumps({"assets": assets}), encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# File integrity
# ---------------------------------------------------------------------------


def test_is_png_positive(tmp_path: Path) -> None:
    p = make_png(tmp_path / "x.png")
    with p.open("rb") as fh:
        head = fh.read(16)
    assert _is_png(head)


def test_is_jpg_positive(tmp_path: Path) -> None:
    p = tmp_path / "x.jpg"
    p.write_bytes(b"\xff\xd8\xff\xe0" + b"junk")
    assert _is_jpg(b"\xff\xd8\xff\xe0")


def test_is_webp_positive(tmp_path: Path) -> None:
    head = b"RIFF\x00\x00\x00\x00WEBP"
    assert _is_webp(head)


def test_zero_byte_file_rejected(tmp_path: Path) -> None:
    p = tmp_path / "zero.png"
    p.write_bytes(b"")
    audit = _audit_one(p, "hand-drawing")
    assert audit["score"] == 0
    assert any("0-byte" in i for i in audit["issues"])


def test_truncated_png_rejected(tmp_path: Path) -> None:
    p = tmp_path / "trunc.png"
    im = Image.new("RGB", (32, 32), (10, 20, 30))
    buf = io = __import__("io").BytesIO()
    im.save(buf, format="PNG")
    data = buf.getvalue()
    # Drop the IEND chunk (last ~12 bytes)
    p.write_bytes(data[:-50])
    audit = _audit_one(p, "hand-drawing")
    assert any("truncated" in i or "bad magic" in i for i in audit["issues"])


def test_small_file_flagged_as_placeholder(tmp_path: Path) -> None:
    p = tmp_path / "tiny.png"
    p.write_bytes(b"\x89PNG\r\n\x1a\n" + b"x" * 100)  # valid magic, < 5KB
    audit = _audit_one(p, "hand-drawing")
    assert any("placeholder" in i or "< 5KB" in i or "only" in i for i in audit["issues"])


# ---------------------------------------------------------------------------
# SHA-256 dedup
# ---------------------------------------------------------------------------


def test_sha256_returns_deterministic_hash(tmp_path: Path) -> None:
    p = make_png(tmp_path / "x.png")
    h1 = _sha256(p)
    h2 = _sha256(p)
    assert h1 == h2
    assert len(h1) == 64


def test_dedup_five_same_files_triggers_global_dup(tmp_path: Path) -> None:
    d = tmp_path / "imgs"
    d.mkdir()
    for i in range(5):
        make_png(d / f"a{i}.png", color=(10, 20, 30))
    result = check_images(d, style="hand-drawing")
    assert any("중복" in i for i in result["issues"])
    assert not result["pass"]


def test_dedup_four_same_files_no_dup_penalty(tmp_path: Path) -> None:
    d = tmp_path / "imgs"
    d.mkdir()
    for i in range(4):
        make_png(d / f"a{i}.png", color=(10, 20, 30))
    result = check_images(d, style="hand-drawing")
    # 4 ≤ 4 ⇒ no global dedup penalty
    assert not any("중복" in i for i in result["issues"])


# ---------------------------------------------------------------------------
# Visual diversity / placeholder detection
# ---------------------------------------------------------------------------


def test_placeholder_color_black_flagged(tmp_path: Path) -> None:
    d = tmp_path / "imgs"
    d.mkdir()
    p = make_png(d / "black.png", color=(0, 0, 0))
    rgb = _mean_rgb(p)
    assert rgb is not None
    audit = _audit_one(p, "hand-drawing")
    assert any("placeholder" in i.lower() or "monochrome" in i.lower() for i in audit["issues"])


def test_placeholder_color_white_flagged(tmp_path: Path) -> None:
    d = tmp_path / "imgs"
    d.mkdir()
    p = make_png(d / "white.png", color=(255, 255, 255))
    audit = _audit_one(p, "hand-drawing")
    assert any("placeholder" in i.lower() for i in audit["issues"])


def test_varied_colors_no_diversity_penalty(tmp_path: Path) -> None:
    d = tmp_path / "imgs"
    d.mkdir()
    for i, color in enumerate([(255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 0)]):
        make_png(d / f"v{i}.png", color=color)
    result = check_images(d, style="hand-drawing")
    assert not any("매우 비슷" in i for i in result["issues"])


def test_similar_colors_diversity_penalty(tmp_path: Path) -> None:
    d = tmp_path / "imgs"
    d.mkdir()
    for i in range(3):
        # all near-grey with tiny variance
        c = (100 + i, 100 + i, 100 + i)
        make_png(d / f"g{i}.png", color=c)
    result = check_images(d, style="hand-drawing")
    # either diversity_note or global note should be present
    note = result["global"].get("diversity_note") or ""
    issues = " ".join(result["issues"])
    assert "비슷" in note or "비슷" in issues or result["global"].get("diversity_note")


# ---------------------------------------------------------------------------
# Style consistency
# ---------------------------------------------------------------------------


def test_style_prefix_present_hand_drawing() -> None:
    prompt = "Masterful hand-drawn ink editorial illustration of a rocket."
    assert _style_prefix_present(prompt, "hand-drawing")


def test_style_prefix_present_oil() -> None:
    prompt = "A rich oil painting style portrait with painterly texture."
    assert _style_prefix_present(prompt, "oil")


def test_style_prefix_missing() -> None:
    prompt = "A flat geometric abstract of a server rack."
    assert not _style_prefix_present(prompt, "hand-drawing")
    assert not _style_prefix_present(prompt, "oil")


def test_image_plan_style_mismatch_logged(tmp_path: Path) -> None:
    d = tmp_path / "imgs"
    d.mkdir()
    make_png(d / "a.png", color=(100, 50, 50))
    plan = write_plan(
        tmp_path,
        [
            {"id": "cover", "style": "hand-drawing", "prompt": "A flat rocket. No style."},
        ],
    )
    result = check_images(d, style="hand-drawing", image_plan_path=plan)
    assert any("hand-drawing" in i or "prefix" in i for i in result["issues"])


# ---------------------------------------------------------------------------
# Aspect ratio & dimensions
# ---------------------------------------------------------------------------


def test_parse_dimensions_png_round_trip(tmp_path: Path) -> None:
    p = make_png(tmp_path / "x.png", size=(1024, 1024))
    dims = _parse_dimensions_png(p)
    assert dims == (1024, 1024)


def test_parse_dimensions_jpg(tmp_path: Path) -> None:
    p = tmp_path / "x.jpg"
    im = Image.new("RGB", (1024, 1024), (10, 20, 30))
    im.save(p, format="JPEG", quality=90)
    dims = _parse_dimensions_jpg(p)
    assert dims == (1024, 1024)


def test_parse_dimensions_webp(tmp_path: Path) -> None:
    p = tmp_path / "x.webp"
    im = Image.new("RGB", (1024, 1024), (10, 20, 30))
    im.save(p, format="WEBP")
    dims = _parse_dimensions_webp(p)
    assert dims == (1024, 1024)


def test_audit_1024x1024_passes_aspect_check(tmp_path: Path) -> None:
    d = tmp_path / "imgs"
    d.mkdir()
    p = make_png(d / "a.png", size=(1024, 1024), color=(200, 100, 50))
    audit = _audit_one(p, "hand-drawing")
    assert not any("aspect ratio" in i for i in audit["issues"])
    assert not any("dimensions" in i for i in audit["issues"])


def test_audit_1920x1080_fails_aspect_check(tmp_path: Path) -> None:
    d = tmp_path / "imgs"
    d.mkdir()
    p = make_png(d / "a.png", size=(1920, 1080), color=(200, 100, 50))
    audit = _audit_one(p, "hand-drawing")
    assert any("aspect ratio" in i for i in audit["issues"])


def test_audit_640x640_fails_side_check(tmp_path: Path) -> None:
    d = tmp_path / "imgs"
    d.mkdir()
    p = make_png(d / "a.png", size=(640, 640), color=(200, 100, 50))
    audit = _audit_one(p, "hand-drawing")
    assert any("dimensions" in i for i in audit["issues"])


# ---------------------------------------------------------------------------
# End-to-end
# ---------------------------------------------------------------------------


def test_check_images_empty_dir_fails(tmp_path: Path) -> None:
    d = tmp_path / "empty"
    d.mkdir()
    result = check_images(d)
    assert result["score"] == 0
    assert not result["pass"]


def test_check_images_passing_folder(tmp_path: Path) -> None:
    d = tmp_path / "imgs"
    d.mkdir()
    for i, color in enumerate([(255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 0), (200, 100, 50)]):
        make_png(d / f"a{i}.png", size=(1024, 1024), color=color)
    result = check_images(d, style="hand-drawing")
    assert result["pass"], result
    assert result["score"] >= DEFAULT_MIN_SCORE
    assert result["global"]["file_count"] == 5


def test_check_images_threshold_override(tmp_path: Path) -> None:
    d = tmp_path / "imgs"
    d.mkdir()
    p = make_png(d / "a.png", size=(1024, 1024), color=(100, 100, 100))
    result = check_images(d, min_score=1)
    # Single image, varied from default assumption, no de-dup, pass at 1.
    assert result["threshold"] == 1
    assert result["pass"]


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def test_cli_passes_on_valid_dir(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    d = tmp_path / "imgs"
    d.mkdir()
    for i, color in enumerate([(255, 0, 0), (0, 255, 0), (0, 0, 255)]):
        make_png(d / f"a{i}.png", size=(1024, 1024), color=color)
    rc = main(["--image-dir", str(d), "--style", "hand-drawing"])
    captured = capsys.readouterr()
    assert rc == 0
    assert "PASS" in captured.out
    assert "image score" in captured.out


def test_cli_fails_on_bad_dir(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    d = tmp_path / "empty"
    d.mkdir()
    rc = main(["--image-dir", str(d), "--style", "hand-drawing"])
    captured = capsys.readouterr()
    assert rc == 1
    assert "FAIL" in captured.out


def test_cli_json_output_machine_readable(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    d = tmp_path / "imgs"
    d.mkdir()
    for i, color in enumerate([(255, 0, 0), (0, 255, 0), (0, 0, 255)]):
        make_png(d / f"a{i}.png", size=(1024, 1024), color=color)
    rc = main(["--image-dir", str(d), "--style", "hand-drawing", "--json"])
    captured = capsys.readouterr()
    parsed = json.loads(captured.out)
    assert isinstance(parsed["score"], int)
    assert "per_image" in parsed
    assert "global" in parsed
    assert rc == 0
