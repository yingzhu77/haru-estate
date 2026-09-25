"""Browser configuration is local-only and protected against cross-site requests."""

import secrets
from urllib.parse import urlsplit

from starlette.requests import Request


def allowed(request: Request, token: str) -> bool:
    loopback = {"localhost", "127.0.0.1", "::1"}
    if request.url.hostname not in loopback:
        return False
    origin = request.headers.get("origin")
    if origin:
        try:
            parsed = urlsplit(origin)
        except ValueError:
            return False
        if parsed.scheme not in {"http", "https"} or parsed.hostname not in loopback:
            return False
    if request.headers.get("sec-fetch-site") == "cross-site":
        return False
    if request.headers.get("x-haru-config") != "1":
        return False
    if request.method != "GET":
        if not secrets.compare_digest(
            request.headers.get("x-haru-csrf", "").encode(), token.encode()
        ):
            return False
        if request.headers.get("content-type", "").split(";")[0] != "application/json":
            return False
    return True
