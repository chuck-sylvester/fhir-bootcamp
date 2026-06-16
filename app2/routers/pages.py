# ---------------------------------------------------------------------
# fhir-bootcamp/app2/routers/pages.py
# ---------------------------------------------------------------------
# UI routes that render Jinja2 HTML templates.
# Add new user-facing pages here as the application grows.
# ---------------------------------------------------------------------

import base64
import json
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app2.config import settings

router = APIRouter()

templates = Jinja2Templates(directory="app2/templates")

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

    # Decode the OIDC ID token so the home page can display identity claims.
    # The raw JWT is retrieved from the server-side store (never the cookie).
    # id_token_claims_json is pre-formatted for direct injection into <pre>.
    id_token_claims = None
    id_token_claims_json = None
    if session_id:
        token_entry = request.app.state.token_store.get(session_id, {})
        raw_id_token = token_entry.get("id_token", "")
        if raw_id_token:
            id_token_claims = _decode_jwt_payload(raw_id_token)
            id_token_claims_json = json.dumps(id_token_claims, indent=2)

    return request.app.state.templates.TemplateResponse(
        request,
        "home.html",
        {
            "session_active": session_active,
            "token_expired": token_expired,
            "expires_display": expires_display,
            "scope": request.session.get("scope", ""),
            # Passed to home.html to conditionally render the ID Token button
            # and dialog. None when there is no session or no id_token in scope.
            "id_token_claims": id_token_claims,
            "id_token_claims_json": id_token_claims_json,
        },
    )


@router.get("/patient", name="patient", response_class=HTMLResponse, include_in_schema=False)
async def patient_portal(request: Request):
    """Renders the patient portal page (portal.html base + patient.html content block)."""
    return templates.TemplateResponse(
        request,
        "patient.html",
        {"title": "Patient Portal"}
    )


@router.get("/fhir/patient", response_class=HTMLResponse, include_in_schema=False)
async def fhir_get_patient(request: Request):
    """
    HTMX endpoint — calls GET /Patient on the Epic FHIR R4 sandbox.

    This is NOT a page route. It returns a small HTML fragment that HTMX
    injects into #result on the patient portal page. The browser never sees
    or transmits the Bearer token — it stays on the server in app.state.token_store.
    """

    # --- 1. Read the session ID from the signed session cookie ---
    # session_id was written during /auth/callback after a successful token
    # exchange. It is the key into app.state.token_store where tokens live.
    session_id = request.session.get("session_id")
    if not session_id:
        return _error_html("No active session. "
                           '<a href="/auth/login">Connect to Epic Sandbox</a> first.')

    # --- 2. Look up the access token in the server-side token store ---
    # token_store is an in-memory dict on app.state (see main.py lifespan).
    # It holds the full Epic token payload keyed by session_id.
    # The access token never travels to the browser — only session_id does.
    token_entry = request.app.state.token_store.get(session_id, {})
    access_token = token_entry.get("access_token")
    if not access_token:
        # Happens when the server restarts and clears in-memory state while
        # the browser still holds an old (now-orphaned) session cookie.
        return _error_html("Session token not found — the server may have restarted. "
                           '<a href="/auth/login">Reconnect to Epic Sandbox</a>.')

    # --- 3. Check whether the access token has already expired ---
    # token_expires_at was stored as an ISO 8601 string in the session cookie
    # during /auth/callback. Checking it here avoids sending a doomed request.
    expires_at_str = request.session.get("token_expires_at")
    if expires_at_str:
        expires_at = datetime.fromisoformat(expires_at_str)
        if datetime.now(timezone.utc) >= expires_at:
            return _error_html("Access token has expired. "
                               '<a href="/auth/login">Reconnect to Epic Sandbox</a>.')

    # --- 4. Call the Epic FHIR API with the Bearer token ---
    # The Authorization header is the only credential Epic needs to identify
    # the caller and enforce the scope granted during OAuth consent.
    # We use app.state.http_client (shared AsyncClient from main.py lifespan)
    # so existing TCP connections to Epic are reused rather than reopened.
    # httpx.TransportError covers all network-level failures (ReadError,
    # ConnectError, TimeoutException, etc.). Without this guard they propagate
    # uncaught, crash the request, and produce a 500 instead of a clean error.
    try:
        response = await request.app.state.http_client.get(
            f"{settings.epic_fhir_base_url}/Patient",
            headers={
                "Authorization": f"Bearer {access_token}",
                # application/fhir+json is the correct MIME type for FHIR R4.
                # Epic also accepts application/json, but fhir+json is preferred.
                "Accept": "application/fhir+json",
            },
        )
    except httpx.TransportError as exc:
        return _error_html(f"Network error contacting Epic FHIR ({type(exc).__name__}). "
                           "Please try again.")

    # --- 5. Handle a non-2xx response from Epic ---
    if not response.is_success:
        return _error_html(
            f"Epic FHIR returned HTTP {response.status_code}.",
            detail=response.text,
        )

    # --- 6. Format the FHIR response and return it as an HTML fragment ---
    # json.dumps with indent=2 pretty-prints the Bundle for readability.
    # HTMX injects this <pre> block directly into #result on the portal page.
    formatted_json = json.dumps(response.json(), indent=2)
    return HTMLResponse(content=f'<pre class="fhir-json">{formatted_json}</pre>')


@router.get("/fhir/medication", response_class=HTMLResponse, include_in_schema=False)
async def fhir_get_medication_request(request: Request):
    """
    HTMX endpoint — calls GET /MedicationRequest on the Epic FHIR R4 sandbox.

    MedicationRequest represents a prescription or medication order for a
    specific patient. Unlike /Patient (which Epic scopes to the session
    automatically), MedicationRequest requires an explicit patient search
    parameter: /MedicationRequest?patient=<fhir_id>.

    The patient FHIR ID is captured from Epic's token response during
    /auth/callback and stored in token_store alongside the access token.
    It is not available in the session cookie.

    NOTE: This endpoint requires the MedicationRequest R4 capability to be
    enabled in the Epic Sandbox app registration. If the capability is not
    yet registered, Epic will return a 403 or 400 error.
    """

    # --- 1. Read the session ID from the signed session cookie ---
    session_id = request.session.get("session_id")
    if not session_id:
        return _error_html("No active session. "
                           '<a href="/auth/login">Connect to Epic Sandbox</a> first.')

    # --- 2. Look up the access token and patient ID in the server-side token store ---
    # Both values were written during /auth/callback. The patient FHIR ID comes
    # from Epic's token response (the "patient" field) and is required as a search
    # parameter for MedicationRequest — the resource is always patient-specific.
    token_entry = request.app.state.token_store.get(session_id, {})
    access_token = token_entry.get("access_token")
    if not access_token:
        return _error_html("Session token not found — the server may have restarted. "
                           '<a href="/auth/login">Reconnect to Epic Sandbox</a>.')

    patient_id = token_entry.get("patient", "")
    if not patient_id:
        # Epic includes "patient" in the token response only for patient-scoped
        # standalone launches. A missing value means the session was not launched
        # in patient context — MedicationRequest cannot be queried without it.
        return _error_html(
            "No patient ID in session. "
            "MedicationRequest requires a patient-scoped launch. "
            "Ensure the <code>launch/patient</code> scope is included and "
            '<a href="/auth/login">reconnect to Epic Sandbox</a>.'
        )

    # --- 3. Check whether the access token has already expired ---
    expires_at_str = request.session.get("token_expires_at")
    if expires_at_str:
        expires_at = datetime.fromisoformat(expires_at_str)
        if datetime.now(timezone.utc) >= expires_at:
            return _error_html("Access token has expired. "
                               '<a href="/auth/login">Reconnect to Epic Sandbox</a>.')

    # --- 4. Call the Epic FHIR API ---
    # MedicationRequest is searched by patient; without the parameter Epic will
    # reject the request. The response is a FHIR Bundle of MedicationRequest
    # resources for this patient.
    try:
        response = await request.app.state.http_client.get(
            f"{settings.epic_fhir_base_url}/MedicationRequest",
            params={"patient": patient_id},
            headers={
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/fhir+json",
            },
        )
    except httpx.TransportError as exc:
        return _error_html(f"Network error contacting Epic FHIR ({type(exc).__name__}). "
                           "Please try again.")

    # --- 5. Handle a non-2xx response from Epic ---
    if not response.is_success:
        return _error_html(
            f"Epic FHIR returned HTTP {response.status_code}.",
            detail=response.text,
        )

    # --- 6. Format and return the FHIR Bundle as an HTML fragment ---
    formatted_json = json.dumps(response.json(), indent=2)
    return HTMLResponse(content=f'<pre class="fhir-json">{formatted_json}</pre>')


def _decode_jwt_payload(token: str) -> dict | None:
    """
    Decodes the payload segment of a JWT without verifying the signature.

    A JWT is three base64url-encoded segments separated by dots:
      header.payload.signature

    The payload is JSON containing the identity claims. Signature verification
    is intentionally skipped here — the token was received from Epic over a
    TLS-secured back-channel during the OAuth callback, so its authenticity is
    already established by the transport. This function is for display only.

    Returns the decoded claims dict, or None if decoding fails for any reason.
    """
    try:
        payload_b64 = token.split(".")[1]
        # base64url omits padding characters; restore them before decoding.
        # The two-step modulo ensures we add 0, 1, 2, or 3 "=" signs as needed.
        padding = 4 - len(payload_b64) % 4
        payload_b64 += "=" * (padding % 4)
        return json.loads(base64.urlsafe_b64decode(payload_b64))
    except Exception:
        return None


def _error_html(message: str, detail: str = "") -> HTMLResponse:
    """Returns a styled HTML error fragment for display inside #result."""
    detail_block = f'<pre class="fhir-error-detail">{detail}</pre>' if detail else ""
    return HTMLResponse(content=f'<p class="fhir-error">{message}</p>{detail_block}')
