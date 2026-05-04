from __future__ import annotations

import pathlib

import httpx


class APIError(Exception):
    def __init__(self, status_code: int, message: str) -> None:
        self.status_code = status_code
        self.message = message
        super().__init__(f"HTTP {status_code}: {message}")


class SessionbinClient:
    def __init__(self, base_url: str, timeout: float = 60.0) -> None:
        self.client = httpx.Client(base_url=base_url, timeout=timeout)

    def upload(self, path: pathlib.Path) -> dict:
        with open(path, "rb") as f:
            resp = self.client.post("/api/upload", files={"file": (path.name, f)})
        if resp.status_code != 200:
            raise self._error(resp)
        return resp.json()

    def delete(self, slug: str, token: str) -> None:
        resp = self.client.delete(f"/api/p/{slug}", headers={"X-Delete-Token": token})
        if resp.status_code != 204:
            raise self._error(resp)

    def _error(self, resp: httpx.Response) -> APIError:
        try:
            body = resp.json()
            message = body.get("error") or body.get("detail") or resp.text
        except Exception:
            message = resp.text or resp.reason_phrase
        return APIError(resp.status_code, message)
