#!/usr/bin/env python3
"""
RISP Progress Tracker — 단계별 진행상황을 텔레그램에 알림.

블로그 + SNS 자동화처럼 1~5분 걸리는 작업 중간에 사용자가
"지금 뭐 하고 있지?" 헷갈리지 않도록 각 단계의 시작/진행/완료/실패를
구조화된 메시지로 텔레그램에 보낸다.

핵심 기능:
- 단계 카운터 (1/5, 2/5, ...) 와 각 단계의 경과 시간, 총 경과
- 평균 단계 시간 기반 ETA 추정
- 진행률(%) 옵션 — 서브스텝이 있는 경우 사용
- 모든 이벤트를 `~/.openclaw/workspace-blogger/data/risp_progress.jsonl`에 append
  (사후 분석 / 평균 시간 산정용)

사용 패턴 (파이프라인):
    progress = ProgressTracker(session_id, total_stages=4)
    progress.begin("📥 요청 접수", f"원문: {url}")
    progress.update("URL 정규화 중...")
    progress.complete(extra="수집 완료")
    ...
    progress.begin("🧵 Threads 발행")
    progress.update("토큰 점검 중...")
    progress.complete(extra="post_id=1234")

사용 패턴 (에이전트 수동 단계, blog 작성):
    progress = ProgressTracker(session_id, total_stages=6)
    progress.begin("🔍 원문 분석", f"URL: {url}")
    # ... fetch URL ...
    progress.update("본문 파싱 중... 30%")
    # ... parse ...
    progress.complete(extra="키워드 5개 추출")
    progress.begin("✍️ 초안 작성", "본문 ~2000자 예상")
    # ... draft ...
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

from .session_signaler import send_message as risp_signal


KST = timezone(timedelta(hours=9))
PROGRESS_LOG = Path.home() / ".openclaw" / "workspace-blogger" / "data" / "risp_progress.jsonl"


def _fmt_duration(seconds: float) -> str:
    """경과 시간을 읽기 좋게 포맷 (예: '2분 14초', '1시간 5분')."""
    if seconds < 1:
        return f"{int(seconds * 1000)}ms"
    if seconds < 60:
        return f"{int(seconds)}초"
    m, s = divmod(int(seconds), 60)
    if m < 60:
        return f"{m}분 {s}초" if s else f"{m}분"
    h, m = divmod(m, 60)
    return f"{h}시간 {m}분" if m else f"{h}시간"


def _fmt_eta(eta_seconds: float | None) -> str:
    if eta_seconds is None or eta_seconds < 0:
        return "—"
    return f"~{_fmt_duration(eta_seconds)}"


class ProgressTracker:
    """
    단계별 진행 추적기.

    모든 begin/update/complete/failed 호출은:
    1) 텔레그램으로 구조화된 진행 메시지 발송
    2) 로컬 risp_progress.jsonl에 append (사후 분석용)
    """

    def __init__(self, session_id: str, total_stages: int = 1, label: str = "RISP"):
        self.session_id = session_id
        self.total_stages = max(1, total_stages)
        self.label = label
        self.stage_index = 0
        self.stage_name = ""
        self.stage_start_ts: float | None = None
        self.overall_start_ts = time.time()
        # Track-A 2026-06-07: 사이클 카운터. complete() 시 stage_index를
        # 0으로 리셋하므로 매 호출이 새 사이클 1번부터 시작되지만,
        # pipeline 전체를 거시적으로 보면 cycle_n으로 몇 번째 시도인지
        # 추적 가능.
        self.cycle_n = 1
        self.cycle_start_ts = self.overall_start_ts
        # 각 단계의 실제 소요 시간을 누적 → 남은 단계 ETA 산정
        self.stage_durations: list[float] = []

    # ─── Public API ─────────────────────────────────────────────

    def begin(self, stage_name: str, details: str = "") -> "ProgressTracker":
        """
        새 단계 시작. 이전 단계가 진행 중이면 자동으로 close.
        """
        if self.stage_name and self.stage_start_ts is not None:
            # 이전 단계가 닫히지 않은 채로 다음 단계 진입 — 이전 단계 시간을 기록
            self.stage_durations.append(time.time() - self.stage_start_ts)

        self.stage_index += 1
        self.stage_name = stage_name
        self.stage_start_ts = time.time()
        elapsed_overall = time.time() - self.overall_start_ts

        eta = self._estimate_remaining_eta()
        msg_lines = [
            f"⏳ [{self.stage_index}/{self.total_stages}] {stage_name} 시작 (cycle {self.cycle_n})",
        ]
        if details:
            msg_lines.append(details)
        msg_lines.append(f"⏱️ 총 경과: {_fmt_duration(elapsed_overall)}")
        if eta and self.stage_index < self.total_stages:
            msg_lines.append(f"🕐 남은 예상: {_fmt_eta(eta)}")

        self._send("\n".join(msg_lines), event="begin")
        return self

    def update(self, details: str, percent: int | None = None) -> "ProgressTracker":
        """
        현재 단계 내 진행 상황 갱신. percent는 0~100, 생략 가능.
        """
        if not self.stage_name:
            # begin 없이 update 호출 → 임시 단계로 처리
            self.begin("진행 중")

        stage_elapsed = time.time() - (self.stage_start_ts or time.time())
        overall_elapsed = time.time() - self.overall_start_ts

        msg_lines = [f"📊 [{self.stage_index}/{self.total_stages}] {self.stage_name}"]
        if percent is not None:
            bar = self._progress_bar(percent)
            msg_lines.append(f"{bar} {percent}%")
        msg_lines.append(details)
        msg_lines.append(f"⏱️ 단계: {_fmt_duration(stage_elapsed)} · 총: {_fmt_duration(overall_elapsed)}")

        self._send("\n".join(msg_lines), event="update", percent=percent)
        return self

    def complete(self, extra: str = "") -> "ProgressTracker":
        """
        현재 단계 완료. 다음 단계 시작 전까지는 update를 보내지 말 것.

        Track-A 2026-06-07 fix: complete() 호출 시 stage_index를 0으로 리셋.
        새 사이클 begin()이 호출될 때 1부터 다시 카운트되도록 만든다. 그래야
        텔레그램 사용자 시야에서 매 사이클이 깔끔한 1/3 → 2/3 → 3/3로 보임.
        stage_name/start_ts도 함께 비워 다음 begin()에서 중복 누적을 막는다.
        """
        if not self.stage_name or self.stage_start_ts is None:
            return self

        stage_elapsed = time.time() - self.stage_start_ts
        self.stage_durations.append(stage_elapsed)
        overall_elapsed = time.time() - self.overall_start_ts
        eta = self._estimate_remaining_eta()

        msg_lines = [f"✅ [{self.stage_index}/{self.total_stages}] {self.stage_name} 완료 (cycle {self.cycle_n})"]
        if extra:
            msg_lines.append(extra)
        msg_lines.append(f"⏱️ 단계: {_fmt_duration(stage_elapsed)} · 총: {_fmt_duration(overall_elapsed)}")
        if eta and self.stage_index < self.total_stages:
            msg_lines.append(f"🕐 남은 예상: {_fmt_eta(eta)}")
        else:
            # 마지막 단계
            if self.stage_index >= self.total_stages:
                msg_lines.append("🎉 전체 파이프라인 완료")

        self._send("\n".join(msg_lines), event="complete")
        # 단계 상태 + stage_index 리셋 (다음 begin에서 새 사이클 1부터 시작)
        self.stage_name = ""
        self.stage_start_ts = None
        self.stage_index = 0
        # 사이클 종료 → 다음 사이클 카운터 증가
        self.cycle_n += 1
        return self

    def failed(self, error: str, hint: str = "") -> "ProgressTracker":
        """
        현재 단계 실패. 워크플로우는 계속 진행해도 되지만 사용자는 즉시 알림을 받음.

        Track-A 2026-06-07: failed()도 complete()와 동일하게 stage_index를
        0으로 리셋. 그래야 사용자가 텔레그램에서 "여전히 같은 단계"라고
        오해하지 않는다. 사이클 카운터도 +1 증가.
        """
        stage_elapsed = time.time() - (self.stage_start_ts or time.time())
        overall_elapsed = time.time() - self.overall_start_ts

        msg_lines = [f"❌ [{self.stage_index}/{self.total_stages}] {self.stage_name} 실패 (cycle {self.cycle_n})"]
        msg_lines.append(error)
        if hint:
            msg_lines.append(f"💡 {hint}")
        msg_lines.append(f"⏱️ 단계: {_fmt_duration(stage_elapsed)} · 총: {_fmt_duration(overall_elapsed)}")

        self._send("\n".join(msg_lines), event="failed", level="error")
        self.stage_name = ""
        self.stage_start_ts = None
        self.stage_index = 0
        self.cycle_n += 1
        return self

    def summary(self) -> "ProgressTracker":
        """
        전체 작업 요약. 모든 단계 종료 후 한 번 호출.

        Track-A 2026-06-07: cycle_n과 stage_durations 합산을 함께 표시.
        """
        total = time.time() - self.overall_start_ts
        avg = (sum(self.stage_durations) / len(self.stage_durations)) if self.stage_durations else 0
        msg = (
            f"📋 {self.label} 요약\n"
            f"• 총 사이클: {self.cycle_n - 1}\n"
            f"• 마지막 사이클의 단계: {self.stage_index}/{self.total_stages}\n"
            f"• 총 시간: {_fmt_duration(total)}\n"
            f"• 평균 단계: {_fmt_duration(avg)}"
        )
        self._send(msg, event="summary")
        return self

    # ─── Internals ─────────────────────────────────────────────

    def _estimate_remaining_eta(self) -> float | None:
        """남은 단계의 평균 소요 시간을 기반으로 ETA 추정."""
        if not self.stage_durations or self.stage_index >= self.total_stages:
            return None
        avg = sum(self.stage_durations) / len(self.stage_durations)
        remaining_stages = self.total_stages - self.stage_index
        return avg * remaining_stages

    def _progress_bar(self, percent: int) -> str:
        percent = max(0, min(100, percent))
        filled = percent // 10
        return "▓" * filled + "░" * (10 - filled)

    def _send(self, message: str, event: str, level: str = "info", percent: int | None = None):
        """텔레그램 발송 + 로컬 진행 로그 append. 발송 실패해도 로그에는 남김.

        Track-A 2026-06-07: cycle_n 필드를 jsonl에 추가해서, 사후 분석 시
        동일 session_id의 몇 번째 사이클인지 즉시 알 수 있도록 한다.
        """
        try:
            risp_signal(self.session_id, message, level=level)
        except Exception as e:
            # signaling 실패는 워크플로우를 막지 않음. 로그에만 남김.
            print(f"[PROGRESS SIGNAL FALLBACK] {level.upper()}: {message[:120]} (err: {e})", flush=True)

        try:
            PROGRESS_LOG.parent.mkdir(parents=True, exist_ok=True)
            entry = {
                "timestamp": datetime.now(KST).isoformat(timespec="seconds"),
                "session_id": self.session_id,
                "label": self.label,
                "event": event,
                "cycle_n": self.cycle_n,
                "stage_index": self.stage_index,
                "total_stages": self.total_stages,
                "stage_name": self.stage_name,
                "percent": percent,
                "overall_elapsed_s": round(time.time() - self.overall_start_ts, 2),
                "stage_elapsed_s": (
                    round(time.time() - self.stage_start_ts, 2) if self.stage_start_ts else None
                ),
                "message": message,
                "level": level,
            }
            with open(PROGRESS_LOG, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception as e:
            print(f"[PROGRESS LOG FALLBACK] {e}", flush=True)
