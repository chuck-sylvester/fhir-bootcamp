# ---------------------------------------------------------------------
# fhir-bootcamp/app2/routers/pages.py
# ---------------------------------------------------------------------
# UI routes that render Jinja2 HTML templates.
# Add new user-facing pages here as the application grows.
# ---------------------------------------------------------------------

from datetime import datetime, timezone

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """Application landing page. Shows session status when authenticated."""
    print("===> processing '/' route...")
    expires_at_str = request.session.get("token_expires_at")

    session_id = request.session.get("session_id")
    session_active = bool(session_id)
    token_expired = False
    expires_display = ""

    expires_at_str = request.session.get("token_expires_at")

    if expires_at_str:
        expires_at = datetime.fromisoformat(expires_at_str)
        token_expired = datetime.now(timezone.utc) >= expires_at
        expires_display = expires_at.strftime("%b %d, %Y at %I:%M %p UTC")

    return request.app.state.templates.TemplateResponse(
        request,
        "home.html",
        {
            "session_active": session_active,
            "token_expired": token_expired,
            "expires_display": expires_display,
            "scope": request.session.get("scope", ""),
        },
    )
