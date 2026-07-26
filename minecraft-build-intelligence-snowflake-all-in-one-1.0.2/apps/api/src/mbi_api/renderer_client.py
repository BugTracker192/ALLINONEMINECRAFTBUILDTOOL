from __future__ import annotations

from urllib.parse import urlparse

import httpx


class RendererServiceError(RuntimeError):
    pass


class RendererServiceClient:
    def __init__(self, base_url: str, timeout_seconds: float = 180.0) -> None:
        parsed = urlparse(base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("renderer service URL must be an absolute HTTP(S) URL")
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = max(1.0, float(timeout_seconds))

    def render(self, payload: dict[str, object]) -> dict[str, object]:
        try:
            with httpx.Client(timeout=self.timeout_seconds, follow_redirects=False) as client:
                response = client.post(f"{self.base_url}/render", json=payload)
        except httpx.HTTPError as exc:
            raise RendererServiceError(f"renderer service unavailable: {exc}") from exc
        if response.status_code != 200:
            try:
                detail = response.json()
            except ValueError:
                detail = {"message": response.text[:1000]}
            raise RendererServiceError(f"renderer service returned {response.status_code}: {detail}")
        result = response.json()
        if not isinstance(result, dict) or not str(result.get("snapshotId", "")).startswith("snap_"):
            raise RendererServiceError("renderer service returned an invalid manifest")
        return result
