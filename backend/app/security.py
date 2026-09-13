"""Browser origin checks for cookie-authenticated writes and WebSockets."""
from urllib.parse import urlsplit

from fastapi import HTTPException, Request, WebSocket

from dashboards.common.config import config


def trusted_origin(origin: str | None, host: str | None) -> bool:
    if not origin or origin == "null" or not host:
        return False
    parsed = urlsplit(origin)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return False
    return parsed.netloc.lower() == host.lower() or origin.rstrip("/") in config.cors_origins


def check_browser_write(request: Request):
    if request.method not in {"POST", "PUT", "PATCH", "DELETE"}:
        return
    # Robot requests authenticate with an API key rather than a browser cookie.
    if request.url.path.startswith("/api/robot/") and request.headers.get("x-anna-robot-key"):
        return
    if request.headers.get("sec-fetch-site") == "cross-site":
        raise HTTPException(status_code=403, detail="Cross-site request rejected.")
    origin = request.headers.get("origin")
    if origin and not trusted_origin(origin, request.headers.get("host")):
        raise HTTPException(status_code=403, detail="Cross-site request rejected.")
    referer = request.headers.get("referer")
    if not origin and referer:
        ref = urlsplit(referer)
        if not trusted_origin(f"{ref.scheme}://{ref.netloc}", request.headers.get("host")):
            raise HTTPException(status_code=403, detail="Cross-site request rejected.")


def websocket_origin_allowed(websocket: WebSocket) -> bool:
    origin = websocket.headers.get("origin")
    # Non-browser test/operations clients may omit Origin but still need auth.
    return not origin or trusted_origin(origin, websocket.headers.get("host"))
