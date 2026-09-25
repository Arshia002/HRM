"""Small JSON client used by the native desktop application."""

from __future__ import annotations

import json
import ssl
import urllib.error
import urllib.parse
import urllib.request
from typing import Any



class ApiError(RuntimeError):
    def __init__(self, message: str, status: int = 0, code: str = ""):
        super().__init__(message)
        self.status = status
        self.code = code


class ApiClient:
    def __init__(self, base_url: str, timeout: float = 12.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.token = ""


    def _ssl_context(self) -> ssl.SSLContext | None:
        parsed = urllib.parse.urlparse(self.base_url)
        if parsed.scheme != "https":
            return None
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        return context

    def request(
        self,
        method: str,
        path: str,
        data: dict[str, Any] | None = None,
        query: dict[str, Any] | None = None,
    ) -> Any:
        url = self.base_url + path
        if query:
            url += "?" + urllib.parse.urlencode(query)
        body = None if data is None else json.dumps(data, ensure_ascii=False).encode("utf-8")
        headers = {"Accept": "application/json"}
        if body is not None:
            headers["Content-Type"] = "application/json; charset=utf-8"
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        request = urllib.request.Request(url, body, headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout, context=self._ssl_context()) as response:
                raw = response.read()
                return json.loads(raw.decode("utf-8")) if raw else None
        except urllib.error.HTTPError as exc:
            try:
                payload = json.loads(exc.read().decode("utf-8"))
            except Exception:
                payload = {}
            raise ApiError(payload.get("error", f"خطای سرویس ({exc.code})"), exc.code, payload.get("code", "")) from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise ApiError("ارتباط با سرور مرکزی برقرار نشد. آدرس و وضعیت شبکه را بررسی کنید.") from exc

    def health(self) -> dict[str, Any]:
        return self.request("GET", "/api/health")

    def login(self, username: str, password: str, otp: str = "") -> dict[str, Any]:
        result = self.request("POST", "/api/login", {"username": username, "password": password, "otp": otp})
        self.token = result["token"]
        return result

    def logout(self) -> None:
        if self.token:
            try:
                self.request("POST", "/api/logout")
            finally:
                self.token = ""
