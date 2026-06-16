# -------------------------------------------------------------------------------
# fhir-bootcamp/app2/routers/auth.py
# -------------------------------------------------------------------------------
# Handles all Epic Sandbox OAuth 2.0 routes:
#
#   GET /auth/login    — builds Epic authorization URL and redirects browser
#   GET /auth/callback — Epic redirects back here after user authorizes;
#                        exchange one-time code for access token via server POST
# -------------------------------------------------------------------------------

import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app2.config import settings

router = APIRouter()

@router.get("/login")
async def auth_login(request: Request, patient: str = ""):
    """
    Step 1 of the OAuth 2.0 Authorization Code flow.

    Constructs the Epic Sandbox authorization URL and issues a 302 redirect,
    sending the user's browser to the Epic login/consent page. After
    the user authorizes, Epic redirects back to /auth/callback with a
    short-lived authorization code.

    The optional `patient` query parameter scopes the session to a specific
    Epic patient ID. Omit it for general staff access.
    """

    # Generate cryptographically random state value
    state = secrets.token_urlsafe(32)
    print(f"===> generated state: {state}...")

    # Store generated state in the session
    request.session["oauth_state"] = state

    params = {
        "response_type": "code",
        "client_id": settings.epic_nonprod_client_id,
        "scope": settings.epic_scope,
        "state": state,
        "redirect_uri": settings.app_redirect_uri,
    }
    # urlencode percent-encodes all special characters, including the forward
    # slashes inside SMART on FHIR scope strings (e.g. user/*.*  →  user%2F*.*)
    # which Epic requires to be encoded in the query string.
    authorization_url = f"{settings.epic_authorize_url}?{urlencode(params)}"
    return RedirectResponse(url=authorization_url)


@router.get("/callback")
async def auth_callback(
    request: Request,
    code: str = None,
    state: str = None,
    error: str = None,
    error_description: str = None,
):
    """
    Step 2 of the OAuth 2.0 Authorization Code flow.

    Epic redirects here after the user logs in. Two outcomes are possible:
      - Success: query string contains `code=<authorization_code>`
      - Failure: query string contains `error=<reason>`

    On success, the authorization code is exchanged for an access token via
    a back-channel POST directly from this server to Epic (the user's
    browser is not involved in the token exchange). The code expires in ~60
    seconds, so the exchange must happen immediately.
    """
    # Epic signals a failed authorization by redirecting here with an
    # `error` parameter instead of a `code`.
    if error:
        raise HTTPException(
            status_code=400,
            detail={"error": error, "error_description": error_description},
        )

    # Read and consume the stored state
    expected_state = request.session.pop("oauth_state", None)

    # Validate
    if not expected_state or state != expected_state:
        raise HTTPException(status_code=400, detail="State mismatch or missing state")

    if not code:
        raise HTTPException(status_code=400, detail="Missing authorization code")

    # Reuse the shared AsyncClient stored on app state at startup rather than
    # opening a new TCP connection for every token exchange.
    http_client: httpx.AsyncClient = request.app.state.http_client

    # httpx.TransportError is the base class for all network-level failures:
    # ReadError (connection reset mid-response), ConnectError (refused),
    # TimeoutException (no response in time), etc. These come from the network
    # between our server and Epic — not from Epic returning an error status.
    # Without this guard they propagate uncaught and produce a 500 crash.
    try:
        response = await http_client.post(
            settings.epic_token_url,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": settings.app_redirect_uri,
                "client_id": settings.epic_nonprod_client_id,
                "client_secret": settings.epic_client_secret
            },
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
            },
        )
    except httpx.TransportError as exc:
        # Surface the exception type (e.g. "ReadError") so it is visible in
        # the browser during development without exposing internal stack traces.
        raise HTTPException(
            status_code=502,
            detail=f"Network error during token exchange with Epic ({type(exc).__name__}). "
                   "Please try connecting again.",
        )

    # A non-2xx status means the token endpoint itself returned an error
    # (wrong secret, expired code, mismatched redirect_uri, etc.).
    if not response.is_success:
        raise HTTPException(
            status_code=502,
            detail=f"Token exchange failed: {response.status_code} {response.text}",
        )

    token_data = response.json()

    # Epic may also signal failure with HTTP 200 but an `error` field in
    # the response body — check for that explicitly.
    if "error" in token_data:
        raise HTTPException(status_code=400, detail=token_data)

    # Clear any data from a previous session before writing the new one.
    # Without this, stale keys loaded from an existing session cookie (e.g.
    # access_token written by an older version of this code) carry over and
    # can push the new cookie over the 4096-byte browser size limit.
    request.session.clear()

    # Generate a short random ID to represent this authenticated session.
    # Only this ID travels to the browser — the tokens themselves stay on
    # the server to avoid exceeding the 4096-byte browser cookie size limit.
    session_id = secrets.token_hex(16)

    # Store the full Epic token payload in the server-side token store, keyed
    # by session_id. See app.state.token_store in main.py for details.
    request.app.state.token_store[session_id] = {
        "access_token": token_data["access_token"],
        "refresh_token": token_data.get("refresh_token", ""),
        "scope": token_data.get("scope", ""),
        # id_token is an OIDC JWT containing identity claims (sub, fhirUser, name,
        # etc.). Present only when the openid scope is granted. Stored server-side
        # alongside access_token so its size does not inflate the browser cookie.
        "id_token": token_data.get("id_token", ""),
        # patient is the FHIR ID of the in-context patient, included by Epic in
        # the token response for patient-scoped standalone launches. Required as
        # a search parameter when querying patient-specific resources such as
        # MedicationRequest (/MedicationRequest?patient=<id>). Empty string when
        # the launch was not patient-scoped (e.g. a provider/staff login).
        "patient": token_data.get("patient", ""),
    }

    # Write only lightweight metadata to the session cookie. The session_id
    # links this cookie back to the token entry above. token_expires_at is
    # stored as ISO 8601 so it survives JSON serialization in the cookie and
    # can be parsed back with fromisoformat().
    request.session["session_id"] = session_id
    request.session["token_expires_at"] = (
        datetime.now(timezone.utc) + timedelta(seconds=token_data["expires_in"])
    ).isoformat()
    request.session["scope"] = token_data.get("scope", "")

    print(f"===> token exchange complete, session_id: {session_id}")
    print(f"===> access_token:\n{token_data['access_token']}")

    # A server-side 302 redirect here would silently drop the session cookie in
    # some browsers (Chrome, Safari) because this response is part of a cross-site
    # redirect chain that originated from Epic's domain. Those browsers treat
    # SameSite=Lax cookies set on 302 responses in that context as ineligible for
    # storage, so the session never reaches the next request.
    #
    # Returning a 200 with a client-side meta-refresh instead causes the browser to
    # fully "land" on our origin before navigating to /, which gives it the
    # opportunity to store the Set-Cookie header normally.
    return HTMLResponse(
        content='<html><head><meta http-equiv="refresh" content="1;url=/"></head></html>'
    )


@router.get("/logout")
async def auth_logout(request: Request):
    """
    Clears the session and redirects to the home page.
    Does not revoke the token at Epic — the access token remains valid
    until it expires naturally. Token revocation is not implemented yet.
    """
    # Remove the token entry from the server-side store before clearing the
    # cookie so the tokens do not linger in memory after the user logs out.
    session_id = request.session.get("session_id")
    if session_id:
        request.app.state.token_store.pop(session_id, None)

    request.session.clear()

    print("===> session cleared.")

    return RedirectResponse(url="/", status_code=302)
