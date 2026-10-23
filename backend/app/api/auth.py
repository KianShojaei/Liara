"""Optional UI password for public deployments.

When COPILOT_UI_PASSWORD is set, every /api route (except /api/auth/*) and the static UI
require a signed session cookie obtained from POST /api/auth/login. The cookie is an HMAC
of a per-install secret, HttpOnly and SameSite=Lax, so it also works for EventSource (SSE),
which cannot send custom headers. Without a password (local use) nothing changes.
"""

from __future__ import annotations

import hashlib
import hmac

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

COOKIE = "copilot_session"
PUBLIC_PATHS = ("/healthz", "/api/auth/login", "/api/auth/status")

router = APIRouter(prefix="/api/auth")


def _token(secret: bytes, password: str) -> str:
    return hmac.new(secret, password.encode(), hashlib.sha256).hexdigest()


def _secret(request: Request) -> bytes:
    rt = request.app.state.runtime
    return rt.store.get_or_create_secret("ui_session_secret")


class Login(BaseModel):
    password: str


@router.get("/status")
def auth_status(request: Request) -> dict[str, bool]:
    password = request.app.state.runtime.settings.copilot_ui_password
    if not password:
        return {"required": False, "authenticated": True}
    cookie = request.cookies.get(COOKIE, "")
    return {
        "required": True,
        "authenticated": hmac.compare_digest(cookie, _token(_secret(request), password)),
    }


@router.post("/login")
def login(body: Login, request: Request, response: Response) -> dict[str, bool]:
    password = request.app.state.runtime.settings.copilot_ui_password
    if not password:
        return {"ok": True}
    if not hmac.compare_digest(body.password, password):
        raise HTTPException(401, "رمز اشتباه است")
    response.set_cookie(
        COOKIE,
        _token(_secret(request), password),
        httponly=True,
        samesite="lax",
        secure=request.url.scheme == "https",
        max_age=60 * 60 * 24 * 30,
    )
    return {"ok": True}


@router.post("/logout")
def logout(response: Response) -> dict[str, bool]:
    response.delete_cookie(COOKIE)
    return {"ok": True}


class UIPasswordMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
        password = (
            request.app.state.runtime.settings.copilot_ui_password
            if hasattr(request.app.state, "runtime")
            else ""
        )
        path = request.url.path
        if not password or path.startswith(PUBLIC_PATHS) or not path.startswith("/api"):
            return await call_next(request)
        cookie = request.cookies.get(COOKIE, "")
        if hmac.compare_digest(cookie, _token(_secret(request), password)):
            return await call_next(request)
        return JSONResponse({"detail": "unauthorized"}, status_code=401)
