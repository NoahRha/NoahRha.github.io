"""Instagram Graph API 클라이언트 — 피드 이미지 게시.

계약(youtube.py 사용부 기준):
    client = InstagramClient(auth.get_instagram_token(), auth.get_instagram_business_account_id())
    result = client.post_feed(image_url, caption)   # -> {"id": "<media_id>"}
image_url은 인터넷에서 접근 가능한 공개 URL이어야 한다(Meta 서버가 직접 내려받음).
"""
from __future__ import annotations

import time

import httpx

GRAPH = "https://graph.facebook.com/v21.0"
# 컨테이너 처리는 비동기 — 생성 직후 publish하면 9007/2207027
# "Media ID is not available"이 난다(2026-09-21 피드 게시 실패).
_CONTAINER_POLL_INTERVAL = 3.0
_CONTAINER_POLL_TIMEOUT = 90.0


class InstagramApiError(RuntimeError):
    def __init__(self, status: int, body: str):
        self.status = status
        self.body = (body or "")[:300]
        super().__init__(f"Instagram API HTTP {status}: {self.body}")


class InstagramClient:
    def __init__(self, access_token: str, ig_user_id: str, timeout: float = 30.0):
        self.token = (access_token or "").strip()
        self.ig_user_id = (ig_user_id or "").strip()
        self.timeout = timeout

    def _post(self, path: str, data: dict) -> dict:
        data = {k: v for k, v in data.items() if v is not None}
        data["access_token"] = self.token
        r = httpx.post(f"{GRAPH}/{self.ig_user_id}/{path}", data=data, timeout=self.timeout)
        if r.status_code != 200:
            raise InstagramApiError(r.status_code, r.text)
        payload = r.json()
        return payload if isinstance(payload, dict) else {}

    def _wait_container(self, creation_id: str) -> None:
        """컨테이너가 FINISHED가 될 때까지 기다린다. ERROR/EXPIRED/타임아웃은 예외."""
        deadline = time.monotonic() + _CONTAINER_POLL_TIMEOUT
        while True:
            r = httpx.get(
                f"{GRAPH}/{creation_id}",
                params={"fields": "status_code", "access_token": self.token},
                timeout=self.timeout,
            )
            if r.status_code != 200:
                raise InstagramApiError(r.status_code, r.text)
            status = str((r.json() or {}).get("status_code") or "").upper()
            if status == "FINISHED":
                return
            if status in {"ERROR", "EXPIRED"}:
                raise InstagramApiError(0, f"미디어 컨테이너 처리 실패(status_code={status})")
            if time.monotonic() >= deadline:
                raise InstagramApiError(0, f"미디어 컨테이너 처리 시간 초과({_CONTAINER_POLL_TIMEOUT:.0f}s)")
            time.sleep(_CONTAINER_POLL_INTERVAL)

    def post_feed(self, image_url: str, caption: str = "") -> dict:
        """이미지 1장 + 캡션 피드 게시. 성공 시 {"id": "<media_id>"}."""
        if not (image_url or "").strip():
            raise InstagramApiError(0, "image_url이 비어 있습니다 — Meta가 직접 내려받을 공개 URL이 필요합니다.")
        container = self._post("media", {"image_url": image_url, "caption": caption or ""})
        creation_id = str(container.get("id") or "").strip()
        if not creation_id:
            raise InstagramApiError(0, "컨테이너 id가 응답에 없습니다.")
        self._wait_container(creation_id)
        published = self._post("media_publish", {"creation_id": creation_id})
        return published if published.get("id") else {"id": ""}

    def post_carousel(self, image_urls: list, caption: str = "") -> dict:
        """이미지 2~10장 카루셀 게시. 각 URL을 children 컨테이너로 만들어 묶어 발행한다."""
        urls = [str(u).strip() for u in (image_urls or []) if str(u).strip()]
        if len(urls) < 2:
            raise InstagramApiError(0, "카루셀에는 공개 이미지 URL이 2개 이상 필요합니다.")
        children: list[str] = []
        for url in urls[:10]:
            container = self._post("media", {"image_url": url, "is_carousel_item": True})
            cid = str(container.get("id") or "").strip()
            if not cid:
                raise InstagramApiError(0, "카루셀 children 컨테이너 id가 응답에 없습니다.")
            children.append(cid)
        for cid in children:
            self._wait_container(cid)
        parent = self._post("media", {"media_type": "CAROUSEL", "children": ",".join(children),
                                      "caption": caption or ""})
        creation_id = str(parent.get("id") or "").strip()
        if not creation_id:
            raise InstagramApiError(0, "카루셀 부모 컨테이너 id가 응답에 없습니다.")
        self._wait_container(creation_id)
        published = self._post("media_publish", {"creation_id": creation_id})
        return published if published.get("id") else {"id": ""}
