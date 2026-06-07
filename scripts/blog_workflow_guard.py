#!/usr/bin/env python3
"""Guard rails for source-blog + SNS publishing jobs.

This script does not write blog content or publish anything. It creates a
small per-job state file and audits that the files promised in status reports
actually exist before build, commit, push, or completion reports.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


KST = timezone(timedelta(hours=9))
WORKSPACE = Path("/Users/noah/.openclaw/workspace-blogger")
STATE_DIR = WORKSPACE / "data" / "workflow-runs"
DEFAULT_POST_DIRS = [WORKSPACE / "content" / "LLM-info", WORKSPACE / "content" / "posts"]
DEFAULT_SNS_DIR = WORKSPACE / "content" / "social"
DEFAULT_IMAGE_ROOT = WORKSPACE / "static" / "images"
HUGO_RETRY_LOG = WORKSPACE / "tmp" / "hugo-build-until-success.log"
IMAGE_PLAN_DIR = WORKSPACE / "data" / "image-plans"
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,120}$")
ALLOWED_IMAGE_MODELS = {
    "gpt-image-2",
    "openai/gpt-image-2",
    "Minimax",
    "minimax",
    "minimax image-01",
    "minimax-portal/image-01",
}
READY_IMAGE_STATUSES = {"reviewed", "approved"}
MINIMAX_REVISION_MIN = 2
# Track-A 2026-06-07: stale check. 마지막 updated_at이 30분 이상 지나면
# 워크플로우가 정체된 것으로 보고 자동 fail 처리한다. 환경변수로 조정.
STALE_AFTER_MINUTES = int(os.environ.get("BLOG_GUARD_STALE_MINUTES", "30"))


def _send_telegram_alert(slug: str, message: str, level: str = "error") -> bool:
    """
    Track-A 2026-06-07: audit 실패 시 무조건 텔레그램으로 알림. session_id는
    workflow state에서 가져오거나 환경변수 fallback. RISP session_signaler의
    3-tier fallback(openclaw → direct http → mavis)을 그대로 사용한다.
    """
    try:
        # Lazy import to avoid pulling risp/ into simple CLI usage.
        sys.path.insert(0, str(WORKSPACE))
        from risp.signaling.session_signaler import send_message

        session_id = _resolve_session_id(slug)
        send_message(session_id, f"[{level.upper()}] [{slug}] {message}", level=level)
        return True
    except Exception as e:
        # fallback: stderr (호출자가 hooks에서 잡을 수 있도록)
        print(f"[TELEGRAM-ALERT-FAILED] [{slug}] {message} (err: {e})", file=sys.stderr)
        return False


def _resolve_session_id(slug: str) -> str:
    """
    workflow state 또는 환경변수에서 텔레그램 라우팅용 session_id를 가져온다.
    형식: 'telegram:<chat_id>[:thread:<thread_id>]' 형태여야 RISP signaler가 인식.
    """
    state_path = state_path_for_slug(slug)
    if state_path.exists():
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
            sid = state.get("telegram_session_id") or state.get("session_id")
            if sid:
                return str(sid)
        except Exception:
            pass

    chat_id = os.environ.get("RISP_TELEGRAM_CHAT_ID") or os.environ.get("TELEGRAM_OWNER_CHAT_ID")
    if chat_id:
        thread_id = os.environ.get("RISP_TELEGRAM_THREAD_ID")
        if thread_id:
            return f"telegram:{chat_id}:thread:{thread_id}"
        return f"telegram:{chat_id}"
    # 마지막 fallback: slug 자체를 session_id처럼 사용. 텔레그램 라우터가
    # 못 찾으면 silent log-only.
    return f"blogger-guard:{slug}"


def state_path_for_slug(slug: str) -> Path:
    """외부에서 slug → state path 조회를 위해 노출 (예: stale check 등)."""
    return STATE_DIR / f"{slug}.json"


def set_blocked_reason(slug: str, reason: str) -> None:
    """
    workflow state에 blocked_reason 필드를 기록한다. harness가 status
    --verbose에서 이 값을 읽어 사용자에게 보여준다.
    """
    path = state_path_for_slug(slug)
    if not path.exists():
        return
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
        state["blocked_reason"] = reason
        state["status"] = "BLOCKED"
        state["updated_at"] = now_kst()
        state.setdefault("notes", []).append(
            {"timestamp": now_kst(), "text": f"blocked: {reason}"}
        )
        path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except Exception as e:
        print(f"[BLOCKED-REASON-WRITE-FAILED] {slug}: {e}", file=sys.stderr)


def is_stale(slug: str, threshold_minutes: int = STALE_AFTER_MINUTES) -> bool:
    """
    마지막 updated_at이 threshold_minutes 이상 지났으면 stale로 본다.
    """
    path = state_path_for_slug(slug)
    if not path.exists():
        return False
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
        updated_at = state.get("updated_at")
        if not updated_at:
            return False
        # ISO format parse
        ts = datetime.fromisoformat(updated_at)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=KST)
        age = datetime.now(KST) - ts
        return age.total_seconds() > threshold_minutes * 60
    except Exception:
        return False


def now_kst() -> str:
    return datetime.now(KST).isoformat(timespec="seconds")


def state_path(slug: str) -> Path:
    validate_slug(slug)
    return STATE_DIR / f"{slug}.json"


def validate_slug(slug: str) -> None:
    if not SLUG_RE.fullmatch(slug):
        raise SystemExit(
            "[BLOCKED] invalid slug. Use lowercase letters, numbers, and hyphens only; "
            "do not include slashes, dots, or spaces."
        )


def load_state(slug: str) -> dict[str, Any]:
    path = state_path(slug)
    if not path.exists():
        raise SystemExit(f"[BLOCKED] workflow state not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def save_state(slug: str, state: dict[str, Any]) -> Path:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    path = state_path(slug)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(WORKSPACE))
    except ValueError:
        return str(path)


def default_post_path(slug: str) -> Path:
    for directory in DEFAULT_POST_DIRS:
        candidate = directory / f"{slug}.md"
        if candidate.exists():
            return candidate
    return DEFAULT_POST_DIRS[0] / f"{slug}.md"


def parse_build_timestamp(line: str) -> datetime | None:
    match = re.match(r"\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) KST\]", line)
    if not match:
        return None
    return datetime.strptime(match.group(1), "%Y-%m-%d %H:%M:%S").replace(tzinfo=KST)


def latest_build_success() -> tuple[str, datetime] | None:
    if not HUGO_RETRY_LOG.exists():
        return None
    success_line = None
    success_time = None
    for line in HUGO_RETRY_LOG.read_text(encoding="utf-8", errors="replace").splitlines():
        if "hugo build succeeded" in line:
            success_line = line.strip()
            success_time = parse_build_timestamp(success_line)
    if not success_line or not success_time:
        return None
    return success_line, success_time


def newest_mtime(paths: list[Path]) -> datetime | None:
    existing = [path for path in paths if path.exists()]
    if not existing:
        return None
    newest = max(path.stat().st_mtime for path in existing)
    return datetime.fromtimestamp(newest, tz=KST)


def git_tracked_or_untracked(path: Path) -> bool:
    result = subprocess.run(
        ["git", "ls-files", "--error-unmatch", rel(path)],
        cwd=WORKSPACE,
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        return True
    # Track-A 2026-06-07: stash 충돌 시 친절한 에러 메시지. untracked/tracked
    # 둘 다 아닌 경우는 거의 (a) stash로 숨겨졌거나 (b) .gitignore에 매칭.
    status = subprocess.run(
        ["git", "status", "--short", "--", rel(path)],
        cwd=WORKSPACE,
        capture_output=True,
        text=True,
    )
    if status.stdout.strip():
        return True
    # 친절한 디버깅: stash / ignore 여부도 같이 본다
    stash = subprocess.run(
        ["git", "stash", "list"],
        cwd=WORKSPACE,
        capture_output=True,
        text=True,
    )
    return False


def diagnose_git_invisibility(path: Path) -> str:
    """
    Track-A 2026-06-07: git_tracked_or_untracked가 False일 때 왜 그런지
    한 줄 진단을 반환. user-facing error에 그대로 붙여 사용자가 즉시
    원인을 알 수 있도록 한다.
    """
    rpa = rel(path)
    ignored = subprocess.run(
        ["git", "check-ignore", "-v", rpa],
        cwd=WORKSPACE, capture_output=True, text=True,
    )
    if ignored.returncode == 0 and ignored.stdout.strip():
        return f"{rpa}는 .gitignore에 매칭되어 git이 추적하지 않습니다 ({ignored.stdout.strip().split(chr(10))[0]})"
    stash = subprocess.run(
        ["git", "stash", "list"],
        cwd=WORKSPACE, capture_output=True, text=True,
    )
    if stash.stdout.strip():
        return f"{rpa}를 추적하지 못합니다. git stash list에 항목이 있어 충돌 가능성 있음. `git stash pop`으로 복원 후 재시도하세요."
    return f"{rpa}가 git 추적/언트랙 상태가 아닙니다. `git add {rpa}`로 스테이징하세요."


def quality_hook_active() -> bool:
    """Quality hook is opt-in. Set ``QUALITY_HOOK=enabled`` to activate.

    Default OFF — Track A's resilience commit touched this file in a parallel
    branch, so we keep the hook disabled until both branches have been
    reviewed and merged. Once activated, the hook delegates to
    ``scripts/quality/review_orchestrator.py`` and adds its findings to the
    audit report.
    """
    return os.environ.get("QUALITY_HOOK", "").strip().lower() in {"1", "true", "yes", "enabled", "on"}


def run_quality_check_translation(post_path: Path, source_url: str) -> tuple[list[str], list[str], dict[str, Any] | None]:
    """Invoke translation_checker in a subprocess and parse its JSON.

    Returns (oks, errors, raw). The subprocess import is intentional: the
    quality package lives under ``scripts/quality/`` and we want the audit
    command to be runnable from a frozen interpreter, not by importing the
    package directly (which would force sys.path surgery inside the
    guard). Errors are caught so a missing/old translation_checker does
    not crash the audit.
    """
    cmd = [
        sys.executable,
        str(WORKSPACE / "scripts" / "quality" / "translation_checker.py"),
        "--post",
        str(post_path),
        "--min-score",
        "70",
        "--json",
    ]
    if source_url:
        cmd.extend(["--source-url", source_url])
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60, cwd=WORKSPACE)
    except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
        return [], [f"translation_checker invocation failed: {exc}"], None
    if result.returncode != 0 and not result.stdout.strip():
        return [], [f"translation_checker failed: {result.stderr.strip() or 'no stdout'}"], None
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        return [], [f"translation_checker output is not JSON: {exc}"], None
    oks: list[str] = []
    errors: list[str] = []
    score = data.get("score", 0)
    threshold = data.get("threshold", 70)
    if data.get("pass"):
        oks.append(f"quality translation score: {score}/{threshold} (pass)")
    else:
        errors.append(
            f"quality translation score {score}/{threshold} < threshold; "
            f"issues: {'; '.join((data.get('issues') or [])[:3])}"
        )
    return oks, errors, data


def run_quality_check_images(
    image_dir: Path, style: str, image_plan: Path | None
) -> tuple[list[str], list[str], dict[str, Any] | None]:
    """Invoke image_checker in a subprocess. See ``run_quality_check_translation``."""
    cmd = [
        sys.executable,
        str(WORKSPACE / "scripts" / "quality" / "image_checker.py"),
        "--image-dir",
        str(image_dir),
        "--style",
        style,
        "--min-score",
        "80",
        "--json",
    ]
    if image_plan is not None:
        cmd.extend(["--image-plan", str(image_plan)])
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120, cwd=WORKSPACE)
    except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
        return [], [f"image_checker invocation failed: {exc}"], None
    if result.returncode != 0 and not result.stdout.strip():
        return [], [f"image_checker failed: {result.stderr.strip() or 'no stdout'}"], None
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        return [], [f"image_checker output is not JSON: {exc}"], None
    oks: list[str] = []
    errors: list[str] = []
    score = data.get("score", 0)
    threshold = data.get("threshold", 80)
    if data.get("pass"):
        oks.append(f"quality images score: {score}/{threshold} (pass, {(data.get('global') or {}).get('file_count', 0)} files)")
    else:
        errors.append(
            f"quality images score {score}/{threshold} < threshold; "
            f"issues: {'; '.join((data.get('issues') or [])[:3])}"
        )
    return oks, errors, data


def find_images(image_dir: Path) -> dict[str, list[Path]]:
    if not image_dir.exists():
        return {"all": [], "cover": [], "threads": [], "instagram": []}
    files = [p for p in image_dir.iterdir() if p.is_file() and p.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}]
    return {
        "all": files,
        "cover": [p for p in files if "cover" in p.name.lower()],
        "threads": [p for p in files if "threads-comic" in p.name.lower()],
        "instagram": [p for p in files if re.search(r"(ig|instagram|card|slide)[-_]?(0?[1-7])", p.name.lower())],
    }


def default_image_plan_path(slug: str) -> Path:
    return IMAGE_PLAN_DIR / f"{slug}.json"


def load_image_plan(plan_path: Path) -> tuple[dict[str, Any] | None, list[str]]:
    if not plan_path.exists():
        return None, [f"image plan missing: {rel(plan_path)}"]
    try:
        return json.loads(plan_path.read_text(encoding="utf-8")), []
    except json.JSONDecodeError as exc:
        return None, [f"image plan is invalid JSON: {rel(plan_path)} ({exc})"]


def audit_image_plan(plan_path: Path, image_dir: Path, mode: str) -> tuple[list[str], list[str], list[Path]]:
    plan, errors = load_image_plan(plan_path)
    oks: list[str] = []
    image_paths: list[Path] = []
    if plan is None:
        return oks, errors, image_paths

    assets = plan.get("assets")
    if not isinstance(assets, list) or not assets:
        return oks, ["image plan has no assets"], image_paths

    asset_ids = {str(asset.get("id") or "") for asset in assets}
    required_ids = {"cover", "threads", "instagram-1", "instagram-2", "instagram-3", "instagram-4", "instagram-5"}
    if mode == "blog":
        required_ids = {"cover"}
    elif mode == "sns":
        required_ids = {"threads", "instagram-1", "instagram-2", "instagram-3", "instagram-4", "instagram-5"}
    missing_ids = sorted(required_ids - asset_ids)
    check(not missing_ids, "image plan contains required asset ids", f"image plan missing required assets: {', '.join(missing_ids)}", errors, oks)

    reviewed_count = 0
    for asset in assets:
        asset_id = str(asset.get("id") or "(missing-id)")
        model = str(asset.get("model") or asset.get("provider") or "")
        status = str(asset.get("status") or "")
        output_path = str(asset.get("output_path") or "")
        aspect_ratio = str(asset.get("aspect_ratio") or "")
        prompt = str(asset.get("prompt") or "").strip()
        attempts = asset.get("attempts")
        review = asset.get("review") or {}

        if model not in ALLOWED_IMAGE_MODELS:
            errors.append(f"image asset {asset_id} uses forbidden model/provider: {model or '(missing)'}")
        if aspect_ratio != "1:1":
            errors.append(f"image asset {asset_id} aspect_ratio must be 1:1")
        if status not in READY_IMAGE_STATUSES:
            errors.append(f"image asset {asset_id} is not ready: status={status or '(missing)'}")
        if not prompt:
            errors.append(f"image asset {asset_id} prompt missing")
        if not isinstance(attempts, list) or not attempts:
            errors.append(f"image asset {asset_id} attempts missing")
        if review.get("claude") not in {"done", "completed", "ok"} and review.get("gpt_fallback") not in {"done", "completed", "ok", "not_needed"}:
            errors.append(f"image asset {asset_id} review state missing")
        if status in {"reviewed", "approved"}:
            reviewed_count += 1
        if not output_path:
            errors.append(f"image asset {asset_id} output_path missing")
            continue
        candidate = Path(output_path)
        if not candidate.is_absolute():
            candidate = WORKSPACE / output_path
        image_paths.append(candidate)
        if not candidate.exists():
            errors.append(f"image asset {asset_id} output file missing: {rel(candidate)}")
        elif image_dir not in candidate.parents and candidate.parent != image_dir:
            errors.append(f"image asset {asset_id} is outside job image dir: {rel(candidate)}")

    check(reviewed_count == len(assets), "all image assets reviewed/approved", f"not all image assets reviewed ({reviewed_count}/{len(assets)})", errors, oks)
    return oks, errors, image_paths


def audit_image_plan_skeleton(plan_path: Path, mode: str) -> tuple[list[str], list[str]]:
    plan, errors = load_image_plan(plan_path)
    oks: list[str] = []
    if plan is None:
        return oks, errors
    assets = plan.get("assets")
    if not isinstance(assets, list) or not assets:
        return oks, ["image plan has no assets"]
    asset_ids = {str(asset.get("id") or "") for asset in assets}
    required_ids = {"cover", "threads", "instagram-1", "instagram-2", "instagram-3", "instagram-4", "instagram-5"}
    if mode == "blog":
        required_ids = {"cover"}
    elif mode == "sns":
        required_ids = {"threads", "instagram-1", "instagram-2", "instagram-3", "instagram-4", "instagram-5"}
    missing_ids = sorted(required_ids - asset_ids)
    check(not missing_ids, "image plan skeleton exists", f"image plan skeleton missing assets: {', '.join(missing_ids)}", errors, oks)
    return oks, errors


def post_image_refs(post_text: str) -> list[str]:
    refs = set(re.findall(r'["(](/images/[^")\s]+)', post_text))
    refs.update(re.findall(r'src="(/images/[^"]+)"', post_text))
    return sorted(ref.split("?")[0] for ref in refs)


def check(condition: bool, ok: str, fail: str, errors: list[str], oks: list[str]) -> None:
    if condition:
        oks.append(ok)
    else:
        errors.append(fail)


def cmd_init(args: argparse.Namespace) -> int:
    validate_slug(args.slug)
    path = state_path(args.slug)
    if path.exists() and not args.force:
        raise SystemExit(f"[BLOCKED] workflow state already exists: {path} (use --force only when restarting intentionally)")
    state = {
        "schema_version": "1.0",
        "slug": args.slug,
        "title": args.title,
        "source_url": args.source_url,
        "style": args.style,
        "mode": args.mode,
        "status": "RECEIVED",
        "created_at": now_kst(),
        "updated_at": now_kst(),
        "paths": {
            "post": rel(default_post_path(args.slug)),
            "sns": rel(DEFAULT_SNS_DIR / f"{args.slug}-sns.md"),
            "image_dir": rel(DEFAULT_IMAGE_ROOT / args.slug),
            "image_plan": rel(default_image_plan_path(args.slug)),
        },
        "required_gates": [
            "source_url_locked",
            "post_file_exists",
            "sns_file_exists",
            "required_images_exist",
            "image_plan_complete",
            "hugo_build_success",
            "claude_or_gpt_review_recorded",
            "minimax_text_revision_recorded",
            "humanize_and_poetry_review_recorded",
        ],
        "review": {
            "claude": "pending",
            "gpt_fallback": "pending",
            "minimax": "pending",
            "minimax_revisions": 0,
            "humanize_korean": "pending",
            "poetry_rhythm": "pending",
        },
        "harness": {
            "enabled": True,
            "intensity": args.harness_intensity,
            "status": "initialized",
        },
        "notes": [],
    }
    path = save_state(args.slug, state)
    print(f"[OK] workflow state initialized: {path}")
    return 0


def cmd_update(args: argparse.Namespace) -> int:
    state = load_state(args.slug)
    state["status"] = args.status
    state["updated_at"] = now_kst()
    if args.note:
        state.setdefault("notes", []).append({"timestamp": now_kst(), "text": args.note})
    if args.claude:
        state.setdefault("review", {})["claude"] = args.claude
    if args.gpt_fallback:
        state.setdefault("review", {})["gpt_fallback"] = args.gpt_fallback
    if args.minimax:
        state.setdefault("review", {})["minimax"] = args.minimax
    if args.minimax_revisions is not None:
        state.setdefault("review", {})["minimax_revisions"] = args.minimax_revisions
    if args.humanize_korean:
        state.setdefault("review", {})["humanize_korean"] = args.humanize_korean
    if args.poetry_rhythm:
        state.setdefault("review", {})["poetry_rhythm"] = args.poetry_rhythm
    if args.harness_status:
        state.setdefault("harness", {})["status"] = args.harness_status
    path = save_state(args.slug, state)
    print(f"[OK] workflow state updated: {path}")
    return 0


def cmd_audit(args: argparse.Namespace) -> int:
    validate_slug(args.slug)
    state = load_state(args.slug)
    paths = state.get("paths") or {}
    post = WORKSPACE / (args.post or paths.get("post") or rel(default_post_path(args.slug)))
    sns = WORKSPACE / (args.sns or paths.get("sns") or rel(DEFAULT_SNS_DIR / f"{args.slug}-sns.md"))
    image_dir = WORKSPACE / (args.image_dir or paths.get("image_dir") or rel(DEFAULT_IMAGE_ROOT / args.slug))
    image_plan = WORKSPACE / (args.image_plan or paths.get("image_plan") or rel(default_image_plan_path(args.slug)))
    source_url = args.source_url or state.get("source_url") or ""
    mode = args.mode or state.get("mode") or "blog-sns"

    errors: list[str] = []
    oks: list[str] = []

    check(bool(source_url), "source URL locked", "source URL is missing in workflow state", errors, oks)
    check(post.exists(), f"post exists: {rel(post)}", f"post file missing: {rel(post)}", errors, oks)
    if post.exists():
        text = post.read_text(encoding="utf-8", errors="replace")
        check("draft: true" not in text.lower(), "post is not draft:true", "post still contains draft: true", errors, oks)
        if source_url:
            check(source_url in text, "post contains locked source URL", "post does not contain locked source URL", errors, oks)
        if args.stage in {"images", "prebuild", "precommit", "complete"}:
            for ref in post_image_refs(text):
                asset = WORKSPACE / "static" / ref.lstrip("/")
                check(asset.exists(), f"referenced image exists: {ref}", f"referenced image missing: {ref}", errors, oks)

    if mode in {"blog-sns", "sns"}:
        check(sns.exists(), f"SNS package exists: {rel(sns)}", f"SNS package missing: {rel(sns)}", errors, oks)
        if sns.exists() and source_url:
            sns_text = sns.read_text(encoding="utf-8", errors="replace")
            has_link_hint = source_url in sns_text or args.slug in sns_text
            check(has_link_hint or args.allow_sns_without_source, "SNS package source/link checked", "SNS package does not contain source URL/blog URL hint", errors, oks)

    image_paths: list[Path] = []
    if args.stage == "draft" and mode in {"blog", "blog-sns", "sns"}:
        skeleton_oks, skeleton_errors = audit_image_plan_skeleton(image_plan, mode)
        oks.extend(skeleton_oks)
        errors.extend(skeleton_errors)

    if args.stage in {"images", "prebuild", "precommit", "complete"}:
        images = find_images(image_dir)
        image_paths = images["all"]
        check(image_dir.exists(), f"image dir exists: {rel(image_dir)}", f"image dir missing: {rel(image_dir)}", errors, oks)
        check(bool(images["all"]), "image dir has image files", f"image dir has no publishable image files: {rel(image_dir)}", errors, oks)
        check(bool(images["cover"]), "cover image exists", "cover image missing (*cover*)", errors, oks)
        if mode == "blog-sns":
            check(bool(images["threads"]), "Threads comic image exists", "Threads comic image missing (*threads-comic*)", errors, oks)
            check(len(images["instagram"]) >= 5, "Instagram 5 images exist", f"Instagram images fewer than 5 ({len(images['instagram'])}/5)", errors, oks)
        plan_oks, plan_errors, plan_paths = audit_image_plan(image_plan, image_dir, mode)
        oks.extend(plan_oks)
        errors.extend(plan_errors)
        image_paths = sorted(set([*image_paths, *plan_paths]))

    # ---- Quality hook (Track B): opt-in via QUALITY_HOOK=enabled ----
    # Runs the deterministic translation/image scorers we added in
    # scripts/quality/. Disabled by default to avoid clashing with Track A's
    # parallel resilience work; once both branches are merged, flip the
    # env var on in the orchestrator to activate.
    if quality_hook_active():
        if args.stage == "draft" and mode in {"blog", "blog-sns"} and post.exists():
            q_oks, q_errs, _ = run_quality_check_translation(post, source_url)
            oks.extend(q_oks)
            errors.extend(q_errs)
        if args.stage in {"images", "prebuild", "precommit", "complete"} and mode in {"blog", "blog-sns"}:
            style = (state.get("style") or "hand-drawing") if isinstance(state.get("style"), str) else "hand-drawing"
            plan_arg: Path | None = image_plan if image_plan.exists() else None
            q_oks, q_errs, _ = run_quality_check_images(image_dir, style, plan_arg)
            oks.extend(q_oks)
            errors.extend(q_errs)

    if args.require_build or args.stage in {"precommit", "complete"}:
        success = latest_build_success()
        check(bool(success), f"Hugo success recorded: {success[0] if success else ''}", "no Hugo success recorded in retry log", errors, oks)
        if success:
            _, success_time = success
            newest_source = newest_mtime([post, sns, *image_paths])
            if newest_source:
                check(
                    success_time >= newest_source,
                    "Hugo success is newer than audited artifacts",
                    "latest Hugo success is older than one or more audited artifacts",
                    errors,
                    oks,
                )

    if args.require_git_visibility or args.stage in {"precommit", "complete"}:
        for path in [post, sns, *image_paths]:
            if path.exists():
                if git_tracked_or_untracked(path):
                    oks.append(f"git sees {rel(path)}")
                else:
                    # Track-A 2026-06-07: 친절한 진단 메시지 (stash / ignore / add 안내)
                    errors.append(f"git does not see {rel(path)}: {diagnose_git_invisibility(path)}")

    review = state.get("review") or {}
    if args.stage in {"draft", "images", "prebuild", "precommit", "complete"} and mode in {"blog", "blog-sns"}:
        minimax_revisions = int(review.get("minimax_revisions") or 0)
        check(
            minimax_revisions >= MINIMAX_REVISION_MIN,
            f"Minimax text revisions recorded ({minimax_revisions})",
            f"Minimax text revisions fewer than {MINIMAX_REVISION_MIN} ({minimax_revisions}/{MINIMAX_REVISION_MIN})",
            errors,
            oks,
        )
        check(
            review.get("minimax") in {"done", "completed", "ok"},
            "Minimax text review recorded",
            "Minimax text review is not recorded as complete",
            errors,
            oks,
        )
        check(
            review.get("humanize_korean") in {"done", "completed", "ok"},
            "humanize-korean pass recorded",
            "humanize-korean pass is not recorded as complete",
            errors,
            oks,
        )
        check(
            review.get("poetry_rhythm") in {"done", "completed", "ok"},
            "poetry/rhythm review recorded",
            "poetry/rhythm review is not recorded as complete",
            errors,
            oks,
        )
    if args.stage in {"precommit", "complete"}:
        claude_done = review.get("claude") in {"done", "completed", "ok"}
        gpt_done = review.get("gpt_fallback") in {"done", "completed", "ok", "not_needed"}
        check(
            claude_done or gpt_done,
            "Claude/GPT review state recorded",
            "Claude/GPT review state is not recorded as complete or fallback",
            errors,
            oks,
        )

    result = {
        "timestamp": now_kst(),
        "slug": args.slug,
        "stage": args.stage,
        "status": "fail" if errors else "ok",
        "ok": oks,
        "errors": errors,
        "stale": is_stale(args.slug),  # Track-A 2026-06-07: 30분 이상 미갱신 경고
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if errors:
        # Track-A 2026-06-07: audit 실패는 무조건 텔레그램으로 알림.
        # 사용자가 "왜 멈추는지 모르는" 상황을 막는다.
        blocked_reason = f"audit {args.stage} 실패: {errors[0]}"
        set_blocked_reason(args.slug, blocked_reason)
        _send_telegram_alert(
            args.slug,
            f"🛑 [{args.slug}] {args.stage} audit 실패\n"
            f"  • 첫 번째 에러: {errors[0]}\n"
            f"  • 전체 에러 수: {len(errors)}\n"
            f"  • 다음 행동: 위 에러를 해결한 뒤 `python3 scripts/blog_workflow_guard.py audit --slug {args.slug} --stage {args.stage}` 재시도",
            level="error",
        )
        return 1

    state["status"] = f"AUDIT_{args.stage.upper()}_OK"
    state["updated_at"] = now_kst()
    # Track-A 2026-06-07: audit 성공 시 blocked_reason 정리
    if "blocked_reason" in state:
        state.pop("blocked_reason", None)
    save_state(args.slug, state)
    return 0


def run_retrospective_hook(slug: str, state: dict[str, Any]) -> None:
    """Generate a retrospective markdown and patch workflow state in-place.

    Best-effort: any exception is allowed to bubble up to the caller, which
    swallows it. Never raises if the feedback module is missing.
    """
    try:
        from feedback.retrospective import (
            extract_lessons,
            load_image_plan,
            render_markdown,
            risp_entries_for_slug,
            telegram_outcomes,
        )
    except ImportError:
        return

    risp_entries = risp_entries_for_slug(slug)
    image_plan = load_image_plan(slug)
    outcomes = telegram_outcomes(state)
    body = render_markdown(slug, state, risp_entries, image_plan, outcomes)

    from feedback.lib import RETRO_DIR, ymd
    from datetime import datetime as _dt

    created = state.get("created_at")
    from feedback.lib import parse_iso_kst, KST

    parsed = parse_iso_kst(created) if created else None
    base = parsed or _dt.now(KST)
    out_dir = RETRO_DIR / ymd(base)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{slug}.md"
    out_path.write_text(body, encoding="utf-8")

    lessons = extract_lessons(state, risp_entries, image_plan, outcomes)
    state["retrospective_path"] = str(out_path)
    state["lessons_learned"] = lessons
    state.setdefault("alerts", [])
    save_state(slug, state)
    print(f"[OK] retrospective written: {out_path}", file=sys.stderr)


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit Blogger workflow state and promised artifacts")
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init", help="Create per-job workflow state")
    init.add_argument("--slug", required=True)
    init.add_argument("--title", required=True)
    init.add_argument("--source-url", required=True)
    init.add_argument("--style", choices=["hand-drawing", "oil"], default="hand-drawing")
    init.add_argument("--mode", choices=["blog", "sns", "blog-sns"], default="blog-sns")
    init.add_argument("--harness-intensity", choices=["strong", "medium", "light"], default="strong")
    init.add_argument("--force", action="store_true", help="Overwrite an existing state file intentionally")
    init.set_defaults(func=cmd_init)

    update = sub.add_parser("update", help="Update per-job workflow state")
    update.add_argument("--slug", required=True)
    update.add_argument("--status", required=True)
    update.add_argument("--note")
    update.add_argument("--claude", choices=["pending", "done", "failed", "skipped"])
    update.add_argument("--gpt-fallback", choices=["pending", "done", "not_needed", "failed"])
    update.add_argument("--minimax", choices=["pending", "done", "failed", "skipped"])
    update.add_argument("--minimax-revisions", type=int)
    update.add_argument("--humanize-korean", choices=["pending", "done", "failed", "skipped"])
    update.add_argument("--poetry-rhythm", choices=["pending", "done", "failed", "skipped"])
    update.add_argument("--harness-status")
    update.set_defaults(func=cmd_update)

    audit = sub.add_parser("audit", help="Audit required files and gates")
    audit.add_argument("--slug", required=True)
    audit.add_argument("--stage", choices=["draft", "images", "prebuild", "precommit", "complete"], default="prebuild")
    audit.add_argument("--mode", choices=["blog", "sns", "blog-sns"])
    audit.add_argument("--source-url")
    audit.add_argument("--post")
    audit.add_argument("--sns")
    audit.add_argument("--image-dir")
    audit.add_argument("--image-plan")
    audit.add_argument("--require-build", action="store_true")
    audit.add_argument("--require-git-visibility", action="store_true")
    audit.add_argument("--allow-sns-without-source", action="store_true")
    audit.set_defaults(func=cmd_audit)

    # Track-A 2026-06-07: stale check command. 30분 이상 미갱신이면
    # 자동 BLOCKED 처리 + 텔레그램 알림.
    stale = sub.add_parser("check-stale", help="Detect workflows not updated within threshold minutes")
    stale.add_argument("--slug")
    stale.add_argument("--threshold-minutes", type=int, default=STALE_AFTER_MINUTES)
    stale.add_argument("--all", action="store_true", help="Check every workflow state file")
    stale.set_defaults(func=cmd_check_stale)

    # Track-A 2026-06-07: 수동 blocker 기록. harness가 status --verbose에서 읽음.
    block = sub.add_parser("mark-blocked", help="Record a blocked_reason in workflow state and alert Telegram")
    block.add_argument("--slug", required=True)
    block.add_argument("--reason", required=True)
    block.set_defaults(func=cmd_mark_blocked)

    args = parser.parse_args()
    return args.func(args)


def cmd_check_stale(args: argparse.Namespace) -> int:
    """
    Track-A 2026-06-07: workflow-runs/의 state 파일 중 마지막 updated_at이
    threshold-minutes 이상 지난 것을 찾아 BLOCKED 처리 + 텔레그램 알림.
    """
    threshold = args.threshold_minutes
    if args.all:
        candidates = sorted(STATE_DIR.glob("*.json"))
    elif args.slug:
        candidates = [state_path_for_slug(args.slug)]
    else:
        print(json.dumps({"error": "specify --slug or --all"}, ensure_ascii=False))
        return 2

    found: list[dict[str, Any]] = []
    for path in candidates:
        if not path.exists():
            continue
        try:
            state = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        slug = state.get("slug") or path.stem
        if not is_stale(slug, threshold_minutes=threshold):
            continue
        reason = f"stale: updated_at > {threshold}분 경과 (마지막 갱신: {state.get('updated_at')})"
        set_blocked_reason(slug, reason)
        _send_telegram_alert(
            slug,
            f"⏰ [{slug}] 워크플로우 정체 감지 (자동 차단)\n"
            f"  • 마지막 updated_at: {state.get('updated_at')}\n"
            f"  • 임계값: {threshold}분\n"
            f"  • 다음 행동: 작업을 이어가거나 `mark-blocked --slug {slug} --reason ...`로 명시적 차단 기록",
            level="warn",
        )
        found.append({"slug": slug, "updated_at": state.get("updated_at"), "reason": reason})

    print(json.dumps({"stale": found, "checked": len(candidates)}, ensure_ascii=False, indent=2))
    return 0 if not found else 1


def cmd_mark_blocked(args: argparse.Namespace) -> int:
    """
    Track-A 2026-06-07: 수동으로 workflow에 blocked_reason을 기록하고
    텔레그램으로 알림. harness status --verbose가 이 값을 사용자에게 노출.
    """
    set_blocked_reason(args.slug, args.reason)
    _send_telegram_alert(
        args.slug,
        f"🛑 [{args.slug}] 수동 차단 기록\n사유: {args.reason}",
        level="error",
    )
    print(json.dumps({"slug": args.slug, "reason": args.reason, "ok": True}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
