#!/usr/bin/env python3
"""
RISP-compliant Blog → SNS continuation pipeline.

This is the single source of truth for both entry points:
- Direct chat after a blog has been published: "SNS까지 진행해"
- Obsidian/blog publish callbacks that already know the public blog URL

Key properties (RISP):
- Immediate Intake + ACK (no silent start)
- SESSION_STATE.json for supervision
- Heavy signaling at every major stage via the RISP signaler
- Automatic progression from confirmed blog URL to real SNS posting
- Uses the production-grade publishing layer (ThreadsPublisher + InstagramPublisher)
- Clear success/failure signals with URLs or next_action

Usage (from blogger agent or handlers):
    python -m risp.orchestration.auto_blog_sns_pipeline \
        --source-url "https://..." \
        --blog-url "https://techllm.github.io/posts/..." \
        --session-id "..." \
        --requester "telegram:554534300" \
        --auto-sns true
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

# RISP imports (our production code)
from ..intake.intake_acknowledger import send_acknowledgment
from ..signaling.session_signaler import send_message as risp_signal
from ..signaling.progress import ProgressTracker
from ..publishing.publish_approved import main as publish_approved_main
from ..state.session_state import update_session_state, get_session_state_path  # convenience wrappers now exist

KST = timezone(timedelta(hours=9))
WORKSPACE_BLOGGER = Path.home() / ".openclaw" / "workspace-blogger"
BLOG_PUBLISHER_SKILL = Path.home() / ".openclaw" / "skills" / "source-blog-publisher" / "SKILL.md"
SNS_APPROVAL_DIR = WORKSPACE_BLOGGER / "data" / "sns-approvals"
SNS_PUBLISH_WRAPPER = WORKSPACE_BLOGGER / "scripts" / "sns" / "parallel_sns_publish.py"
BLOCKED_NO_APPROVAL_LOG = (
    "SNS approval log is required for real publishing. Refusing to create a "
    "temporary approval log with empty media_files."
)

# Track-A 2026-06-07: 동일 session_id로 blog_url 없이 run_pipeline이 N회
# 반복 호출되면 무한 루프로 간주하고 BLOCKED_LOOP로 종료한다.
# 기본값 3회. 환경변수 RISP_MAX_BLOCKED_CYCLES로 조정 가능.
MAX_BLOCKED_CYCLES = int(os.environ.get("RISP_MAX_BLOCKED_CYCLES", "3"))


class CycleTracker:
    """
    session_id별 blog_url-미전달 호출 횟수를 추적하는 작은 추상화.
    기본 구현은 디스크(risp_state/)에 영속화하지만, 테스트에서는
    Mock으로 대체해 디스크 상태와 분리할 수 있다.
    """

    def read(self, session_id: str) -> int:
        try:
            state_path = get_session_state_path(session_id)
            if not state_path.exists():
                return 0
            with open(state_path, encoding="utf-8") as f:
                state = json.load(f)
            return int(state.get("cycle_n", 0))
        except Exception:
            return 0

    def bump(self, session_id: str, increment: int = 1) -> int:
        new_value = self.read(session_id) + increment
        try:
            update_session_state(session_id, "CYCLE_TRACKED", cycle_n=new_value)
        except Exception:
            pass
        return new_value


def _read_cycle_count(session_id: str) -> int:
    """
    session_state에 기록된 cycle_n 값을 읽어온다.
    state 파일이 없거나 cycle_n이 없으면 0 반환.
    """
    try:
        state_path = get_session_state_path(session_id)
        if not state_path.exists():
            return 0
        with open(state_path, encoding="utf-8") as f:
            state = json.load(f)
        return int(state.get("cycle_n", 0))
    except Exception:
        return 0


def _bump_cycle_count(session_id: str, increment: int = 1) -> int:
    """
    state에 cycle_n을 increment만큼 더하고 새 값을 반환.
    state 파일이 없으면 새로 만든다.
    """
    new_value = _read_cycle_count(session_id) + increment
    try:
        update_session_state(session_id, "CYCLE_TRACKED", cycle_n=new_value)
    except Exception:
        # state 저장 실패는 무한 루프 방지에 우선순위가 낮다.
        pass
    return new_value


def now_kst() -> str:
    return datetime.now(KST).isoformat(timespec="seconds")


def signal(session_id: str, message: str, level: str = "info"):
    """Centralized RISP signaling (goes to Telegram in real setup)."""
    try:
        risp_signal(session_id, message, level=level)
    except Exception as e:
        print(f"[RISP SIGNAL FALLBACK] {level.upper()}: {message} (error: {e})", file=sys.stderr)


def run_blog_creation(source_url: str, session_id: str) -> dict:
    """
    Blog creation remains owned by the source-blog-publisher skill.
    This pipeline intentionally refuses to fake that step when no blog_url is
    provided, because source-blog-publisher is a skill workflow rather than a
    callable Python function.
    """
    signal(session_id, "📝 블로그 작성은 source-blog-publisher 스킬에서 먼저 완료해야 합니다.")

    return {
        "success": False,
        "error": (
            "blog_url is required. Run source-blog-publisher first, then call this pipeline "
            "with --blog-url and, when available, --approval-log."
        ),
        "source_url": source_url,
    }


def auto_publish_sns(blog_url: str, session_id: str, approval_log_path: Optional[Path] = None, progress: Optional[ProgressTracker] = None) -> dict:
    """
    Automatic real SNS publishing using our production RISP publishing layer.
    Use this only after blog content and SNS approval assets are prepared.

    progress: 외부 ProgressTracker가 주어지면 그 안에 단계로 기록한다.
              None이면 기존 signal() 호출만 수행 (단독 호출 시).
    """
    if progress is not None:
        progress.begin("🚀 SNS 자동 게시", f"대상: {blog_url}\n플랫폼: Threads + Instagram + Facebook(활성화 시)")
    else:
        signal(session_id, f"🚀 SNS 자동 게시 시작 (자동 모드)\n대상: {blog_url}")

    if approval_log_path is None:
        approval_log_path = find_latest_approval_log(blog_url)
        if approval_log_path:
            signal(session_id, f"📦 기존 SNS 승인 로그 감지: {approval_log_path}")

    if not approval_log_path:
        signal(session_id, f"🛑 SNS 자동 게시 차단: {BLOCKED_NO_APPROVAL_LOG}", level="warn")
        if progress is not None:
            progress.failed(
                BLOCKED_NO_APPROVAL_LOG,
                hint="blog-sns-publisher로 승인 로그와 플랫폼별 이미지/문안을 먼저 생성하세요.",
            )
        return {
            "success": False,
            "blocked": True,
            "error": BLOCKED_NO_APPROVAL_LOG,
            "next_action": "Create or pass --approval-log with approved Threads/Instagram media before publishing.",
        }

    validation_error = validate_approval_log_for_real_publish(approval_log_path)
    if validation_error:
        signal(session_id, f"🛑 SNS 자동 게시 차단: {validation_error}", level="warn")
        if progress is not None:
            progress.failed(validation_error, hint="승인 로그의 문안/이미지/상태를 보완한 뒤 재시도하세요.")
        return {"success": False, "blocked": True, "error": validation_error}

    # Preferred path when an approval log with prepared content exists:
    # Use the SNS wrapper so the normal standalone Facebook publisher is
    # included when the approval log enables Facebook.
    try:
        if progress is not None:
            progress.update("승인 로그 기반 게시 진입")
        exit_code = run_sns_publish_wrapper(approval_log_path, session_id=session_id, dry_run=False)
        success = exit_code == 0
        if progress is not None:
            progress.complete(extra="전체 플랫폼 게시 종료 (성공)" if success else "전체 플랫폼 게시 종료 (일부 실패)")
        else:
            signal(session_id, "✅ SNS 자동 게시 플로우 완료" if success else "⚠️ SNS 자동 게시 플로우 완료 (일부 실패)")
        return {"success": success, "used_approval_log": str(approval_log_path)}
    except Exception as e:
        if progress is not None:
            progress.failed(str(e), hint="publish_approved가 예외를 던졌습니다")
        else:
            signal(session_id, f"❌ SNS 자동 게시 중 예외: {e}", level="error")
        return {"success": False, "error": str(e)}


def run_sns_publish_wrapper(approval_log_path: Path, session_id: str, dry_run: bool = False) -> int:
    """Run the unified SNS publish wrapper from the auto pipeline."""
    if not SNS_PUBLISH_WRAPPER.exists():
        # Fallback keeps the older Threads/Instagram path available if the
        # wrapper is missing, but reports the missing Facebook bridge clearly.
        signal(
            session_id,
            f"⚠️ SNS publish wrapper missing: {SNS_PUBLISH_WRAPPER}. Threads/Instagram만 기존 RISP 경로로 진행합니다.",
            level="warn",
        )
        return publish_approved_main(approval_log_path, dry_run=dry_run, session_id=session_id)

    cmd = [
        "/opt/homebrew/bin/python3",
        str(SNS_PUBLISH_WRAPPER),
        str(approval_log_path),
        "--session-id",
        session_id,
    ]
    if dry_run:
        cmd.append("--dry-run")

    result = subprocess.run(cmd, cwd=str(WORKSPACE_BLOGGER), text=True)
    return result.returncode


def _threads_body(threads: dict) -> str:
    """Threads 본문 텍스트. 3단 스레드(posts 배열)와 단일 content를 모두 인정한다.

    현재 파이프라인은 Threads를 3단 스레드로 만들고 승인 로그에 `posts` 배열로
    적는다(1편 → 답글 → 답글). 예전에는 여기서 `content`/`selected_content`만
    확인해, posts만 있는 로그를 전부 "content is empty"로 막았다. 공개 블로그에서
    복원한 합성 승인 로그가 모두 posts 형식이라 그 경로의 Threads 게시가 항상
    차단됐고, 재시도해도 같은 로그를 다시 만들어 동일하게 실패했다.
    """
    direct = str(threads.get("content") or threads.get("selected_content") or "").strip()
    if direct:
        return direct
    parts = [
        str((post or {}).get("content") or "").strip()
        for post in (threads.get("posts") or [])
        if isinstance(post, dict)
    ]
    return "\n\n".join(part for part in parts if part).strip()


def validate_approval_log_for_real_publish(path: Path) -> Optional[str]:
    """Block real publishing when an approval log lacks required media/content."""
    try:
        log = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return f"approval log not found: {path}"
    except json.JSONDecodeError as exc:
        return f"approval log is invalid JSON: {path} ({exc})"

    platforms = log.get("platforms") or {}
    threads = platforms.get("threads") or {}
    instagram = platforms.get("instagram") or {}

    if threads.get("enabled") and not _threads_body(threads):
        return "Threads is enabled but content is empty."

    if instagram.get("enabled"):
        status = str(instagram.get("status") or "").lower()
        if "blocked" in status or "rate_limit_2207051" in status:
            return "Instagram is already marked as API-blocked; do not retry until Meta clears the action block."
        media_files = instagram.get("media_files") or []
        media_type = str(instagram.get("media_type") or "FEED").upper()
        if not media_files:
            return "Instagram is enabled but media_files is empty."
        if media_type == "CAROUSEL" and len(media_files) < 2:
            return "Instagram carousel requires at least 2 media_files."

    return None


def find_latest_approval_log(blog_url: Optional[str]) -> Optional[Path]:
    if not blog_url or not SNS_APPROVAL_DIR.exists():
        return None

    candidates = []
    for path in SNS_APPROVAL_DIR.glob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        published_url = data.get("blog", {}).get("published_url")
        if published_url == blog_url:
            candidates.append(path)

    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def run_pipeline(
    source_url: str,
    session_id: str,
    requester: str = "unknown",
    auto_sns: bool = True,
    blog_url: Optional[str] = None,
    approval_log_path: Optional[Path] = None,
    # Dependency injection for testability and clean architecture (RISP style)
    intake_func=None,
    signaler=None,
    state_manager=None,
    blog_creator=None,
    sns_publisher=None,
    max_blocked_cycles: Optional[int] = None,
    cycle_tracker: Optional[CycleTracker] = None,
) -> dict:
    """
    Main entry point for the unified automatic Blog + SNS flow.
    Call this after source-blog-publisher has produced a public blog_url.

    Track-A 2026-06-07: 동일 session_id로 blog_url 없이 호출되는 사이클이
    max_blocked_cycles(기본 3)를 넘으면 BLOCKED_LOOP로 종료한다. 이 보호
    장치가 없으면 cron이 blog_url을 결정 못 한 채로 run_pipeline을 10초마다
    재호출하면서 텔레그램에 "1/3 → 2/3"이 무한히 반복된다.

    cycle_tracker 인자로 디스크-기반 영속 카운터를 Mock으로 대체할 수 있다.
    """
    if max_blocked_cycles is None:
        max_blocked_cycles = MAX_BLOCKED_CYCLES
    _cycle = cycle_tracker or CycleTracker()

    # === RISP INTAKE (mandatory, immediate) ===
    _state = state_manager or type(
        'obj',
        (object,),
        {'update_status': lambda self, sid, status, **extra: update_session_state(sid, status, **extra)}
    )()
    _signal = signaler or signal
    _intake = intake_func or send_acknowledgment

    # === Loop guard (Track-A) ===
    # blog_url이 없는 상태에서 호출될 때만 cycle_n을 센다. blog_url이 있는
    # 정상 호출은 사이클 0으로 통과한다.
    prior_cycle = _cycle.read(session_id)
    if not blog_url and prior_cycle >= max_blocked_cycles:
        blocker = (
            f"BLOCKED_LOOP: 동일 session '{session_id}'가 blog_url 없이 "
            f"{prior_cycle}회 호출됨 (한계 {max_blocked_cycles}). "
            f"source-blog-publisher 스킬을 먼저 실행해서 blog_url을 만들고, "
            f"--blog-url 옵션으로 직접 전달해야 합니다."
        )
        _state.update_status(session_id, "BLOCKED_LOOP", reason=blocker, cycle_n=prior_cycle)
        _signal(session_id, f"🛑 {blocker}", level="error")

        # Track-A: ProgressTracker를 임시로 만들어 failed()로 텔레그램 가시성 확보
        try:
            _guard_progress = ProgressTracker(
                session_id, total_stages=1, label="RISP Guard"
            )
            _guard_progress.begin("🛑 무한 루프 차단")
            _guard_progress.failed(
                blocker,
                hint=(
                    "형님, blog_url이 결정되지 않은 채로 run_pipeline이 반복 호출되고 있습니다. "
                    "source-blog-publisher 스킬을 먼저 돌려서 public blog_url을 만든 다음, "
                    "--blog-url로 명시 전달해야 합니다."
                ),
            )
        except Exception:
            pass
        return {
            "success": False,
            "blocked": True,
            "blocked_reason": "BLOCKED_LOOP",
            "error": blocker,
            "cycle_n": prior_cycle,
            "max_cycles": max_blocked_cycles,
            "next_action": (
                "source-blog-publisher 스킬을 직접 실행하여 blog_url을 만들고, "
                "run_pipeline을 --blog-url=<url>과 함께 호출하세요."
            ),
        }

    # === Progress tracker setup ===
    # 파이프라인이 거치는 전체 단계 수를 미리 선언 → ETA 추정에 사용
    # (auto_sns=True 가정, blog creation은 agent가 이미 끝낸 채로 진입)
    total_stages = 3 if auto_sns else 2  # 1=접수, 2=블로그확인, 3=SNS
    progress = ProgressTracker(session_id, total_stages=total_stages, label="RISP Blog+SNS")

    # blog_url이 없을 때만 cycle 카운트 증가 (정상 호출은 사이클 0으로 통과)
    if not blog_url:
        new_cycle = _cycle.bump(session_id, increment=1)
        progress.cycle_n = new_cycle

    _state.update_status(
        session_id, "RECEIVED",
        source_url=source_url, requester=requester, auto_sns=auto_sns,
    )

    summary = f"블로그 후속 SNS 게시 요청 접수\n원문: {source_url}\n블로그 URL: {blog_url or '(미전달)'}"
    _intake(session_id, summary)

    # 1단계: 요청 접수
    progress.begin("📥 요청 접수 (RISP Intake)", f"원문: {source_url}\n요청자: {requester}\n세션: {session_id}")
    _signal(session_id, f"📥 요청 접수 완료 (RISP Intake)\n세션: {session_id}\n원문: {source_url}")
    progress.complete(extra="Intake ACK 발송됨 → 후속 단계 진입")

    try:
        # 2단계: 블로그 발행 확인 (보통 agent가 이미 끝낸 상태로 진입)
        _signal(session_id, f"📝 블로그 발행 확인 시작\nblog_url: {blog_url or '(pipeline 내부에서 결정)'}")
        progress.begin("📝 블로그 발행 확인", f"blog_url: {blog_url or '(pipeline 내부에서 결정)'}")

        if blog_url:
            blog_result = {"success": True, "blog_url": blog_url}
        else:
            _blog_creator = blog_creator or run_blog_creation
            _signal(session_id, "📝 blog_url 미전달: source-blog-publisher 단계가 먼저 필요합니다.")
            progress.update("blog_url 미전달 → 블로그 작성 스킬 선행 필요")
            blog_result = _blog_creator(source_url, session_id)

        if not blog_result.get("success"):
            _state.update_status(session_id, "BLOG_FAILED", error=blog_result)
            progress.failed(str(blog_result.get("error", blog_result)), hint="blog_url을 --blog-url로 직접 전달해 재시도 가능")
            _signal(session_id, f"❌ 블로그 작성 실패: {blog_result}", level="error")
            progress.summary()
            return blog_result

        blog_url = blog_url or blog_result.get("blog_url")
        if not blog_url:
            _signal(session_id, "ℹ️ 블로그 작성 단계 완료. 공개 URL 확인 대기 중...")
            progress.update("공개 URL 확인 대기 중... (cron이 빌드/배포 중일 수 있음)")

        _state.update_status(session_id, "BLOG_PUBLISHED", blog_url=blog_url)

        _signal(session_id, f"✅ 블로그 발행 완료\n{blog_url or '(URL 확인 중)'}")
        progress.complete(extra=f"URL: {blog_url or '(미확인)'}")

        if not auto_sns:
            _signal(session_id, "ℹ️ auto_sns=False → SNS 자동 게시 스킵")
            progress.summary()
            return {"success": True, "blog_url": blog_url, "sns": "skipped"}

        # 3단계: SNS 자동 게시 (auto_publish_sns 내부에서 begin/complete)
        _state.update_status(session_id, "SNS_PUBLISHING_STARTED")
        _signal(session_id, "📣 SNS 자동 게시 플로우 진입 (실제 게시 모드)")

        _sns_publisher = sns_publisher or auto_publish_sns
        sns_result = _sns_publisher(
            blog_url=blog_url or source_url,
            session_id=session_id,
            approval_log_path=approval_log_path,
            progress=progress,  # ProgressTracker를 넘겨서 내부에서 begin/complete
        )

        final_status = "COMPLETED" if sns_result.get("success") else "SNS_PARTIAL_FAILURE"
        _state.update_status(session_id, final_status, sns_result=sns_result)

        if sns_result.get("success"):
            _signal(session_id, "🎉 블로그 후속 SNS 게시 완료!")
        else:
            _signal(session_id, f"⚠️ SNS 일부 실패 (자세한 내용은 위 신호 참조)\n다음 행동이 필요할 수 있습니다.", level="warn")

        # 전체 요약 (평균 단계 시간, 총 소요 등)
        progress.summary()

        return {
            "success": sns_result.get("success", False),
            "blog_url": blog_url,
            "sns_result": sns_result,
        }

    except Exception as e:
        _state.update_status(session_id, "FAILED", error=str(e))
        _signal(session_id, f"💥 파이프라인 예외 발생: {e}", level="error")
        progress.failed(str(e), hint="워크플로우가 예외로 중단되었습니다")
        progress.summary()
        return {"success": False, "error": str(e)}


def main():
    parser = argparse.ArgumentParser(description="RISP Blog-to-SNS continuation pipeline")
    parser.add_argument("--source-url", required=True)
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--requester", default="unknown")
    parser.add_argument("--auto-sns", action="store_true", default=True)
    parser.add_argument("--blog-url")
    parser.add_argument("--approval-log", type=Path)
    args = parser.parse_args()

    result = run_pipeline(
        source_url=args.source_url,
        session_id=args.session_id,
        requester=args.requester,
        auto_sns=args.auto_sns,
        blog_url=args.blog_url,
        approval_log_path=args.approval_log,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    sys.exit(0 if result.get("success") else 1)


if __name__ == "__main__":
    main()
