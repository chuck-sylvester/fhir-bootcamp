# app2 — Epic Sandbox OAuth 2.0 Integration

app2 is a server-side rendered FastAPI web application that authenticates users against the Epic Sandbox via the **SMART on FHIR OAuth 2.0 Authorization Code flow**. After login, it holds an access token that can be used to make FHIR R4 API calls on behalf of the authenticated user. The UI is built with Jinja2 templates and plain CSS; no JavaScript framework is used.

---

## What app2 Does

- Presents a landing page with a "Connect to Epic Sandbox" button
- Redirects the user to Epic's login/consent page (OAuth 2.0 authorization)
- Receives the authorization code callback from Epic
- Exchanges the code for an access token via a server-to-server POST (back-channel)
- Stores the access token server-side; places only a lightweight session cookie in the browser
- Displays session status (active/expired), token expiration time, and granted scopes on the home page
- Supports logout (clears session cookie and removes server-side token)
- Provides a patient portal page with a button that calls the Epic FHIR R4 `GET /Patient` endpoint and renders the result inline using HTMX

---

## Directory Structure

```
app2/
├── __init__.py             # Required for dot-notation uvicorn invocation
├── config.py               # Pydantic Settings — reads from root .env
├── main.py                 # FastAPI app: lifespan, middleware, router registration
├── routers/
│   ├── auth.py             # OAuth routes: /auth/login, /auth/callback, /auth/logout
│   └── pages.py            # UI routes: / (home), /patient, /fhir/patient (HTMX)
├── static/
│   ├── css/main.css
│   └── image/favicon-fhir-72.ico
└── templates/
    ├── home.html           # Jinja2 template: landing / session status page
    ├── portal.html         # Jinja2 base layout for portal pages (template inheritance)
    └── patient.html        # Patient portal page — extends portal.html
```

---

## Dependencies

All dependencies are shared at the project root in `requirements.txt`. Versions are pinned.

| Package | Version | Purpose |
|---|---|---|
| `fastapi[standard]` | 0.136.3 | Web framework; includes uvicorn, python-multipart |
| `jinja2` | 3.1.6 | Server-side HTML templating |
| `httpx` | 0.28.1 | Async HTTP client for back-channel token exchange |
| `itsdangerous` | 2.2.0 | Session cookie signing (required by Starlette SessionMiddleware) |
| `pydantic` | 2.9.2 | Data validation and settings models |
| `pydantic-settings` | 2.14.1 | `.env` file loading via `BaseSettings` |
| `python-dotenv` | 1.2.2 | `.env` file support |

Install from the project root:

```bash
pip install -r requirements.txt
```

---

## Environment Variables

All configuration is stored in `.env` at the project root (not committed to git). app2 reads from this file via `app2/config.py`.

```dotenv
# Application
APP_NAME="FHIR Bootcamp - app2"
APP_ENV=development
APP_DEBUG=True
SESSION_SECRET_KEY=<random-string-at-least-32-chars>

# Epic Sandbox OAuth 2.0
EPIC_NONPROD_CLIENT_ID=<your-epic-app-client-id>
EPIC_CLIENT_SECRET=<your-epic-app-client-secret>
EPIC_AUTHORIZE_URL=https://fhir.epic.com/interconnect-fhir-oauth/oauth2/authorize
EPIC_TOKEN_URL=https://fhir.epic.com/interconnect-fhir-oauth/oauth2/token
EPIC_FHIR_BASE_URL=https://fhir.epic.com/interconnect-fhir-oauth/api/FHIR/R4
EPIC_SCOPE="openid fhirUser"
APP_REDIRECT_URI=http://localhost:8000/auth/callback
```

**Notes on specific variables:**

- `SESSION_SECRET_KEY`: Used by Starlette's `SessionMiddleware` to sign the session cookie with `itsdangerous.TimestampSigner`. Must be a long random string. Generate one with `python -c "import secrets; print(secrets.token_hex(32))"`.
- `EPIC_CLIENT_SECRET`: Use the raw secret value shown immediately after creating the app in the Epic developer portal. The portal later displays a hashed/masked version — use only the original value shown at creation time.
- `EPIC_SCOPE`: Keep this minimal. Epic returns the full set of approved scopes in the token response, and storing a large scope string in the session cookie can exceed the browser's 4096-byte cookie size limit. See the **Scope and Cookie Size** section below.

---

## Epic Sandbox App Registration

App2 uses a **confidential client** registration. A confidential client is appropriate for server-side applications (like this FastAPI SSR app) that can securely hold a client secret — as opposed to public clients (SPAs, mobile apps) where the secret would be exposed.

### Steps

1. Log in to the Epic developer portal at [open.epic.com](https://open.epic.com)
2. Navigate to **My Apps** → **Create**
3. Fill in the app details:
   - **Application Audience**: Patients
   - **Is Confidential Client**: Yes (check this box — required for server-side apps)
   - **Redirect URI**: `http://localhost:8000/auth/callback`
   - **Scopes**: Select only what the app needs. Selecting "All FHIR R4 scopes" results in a ~5000-character scope string in the token response, which breaks the session cookie. See the **Scope and Cookie Size** section.
4. Submit and wait for Epic to provision the app (may take a few minutes for the sandbox)
5. Copy the **Client ID** → set as `EPIC_NONPROD_CLIENT_ID` in `.env`
6. Copy the **Client Secret** shown immediately after creation → set as `EPIC_CLIENT_SECRET` in `.env`

**JWK Set URLs**: Leave blank. These are only needed for `private_key_jwt` client authentication. This app uses `client_secret_post` (client credentials sent in the POST body), so no JWK configuration is needed.

**Persistent access**: Not required unless the app needs to make FHIR calls in the background while the user is offline. App2 only makes calls during an active user session.

---

## OAuth 2.0 Authorization Code Flow

App2 implements the standard SMART on FHIR Authorization Code flow. The steps below describe what happens at runtime. Steps involving the Epic Auth Server are **front-channel**: the browser follows each redirect and its address bar changes at each step. The token exchange (**back-channel**) is server-to-server — app2 contacts Epic's token endpoint directly, and the browser never receives or transmits the access token.

### Step 1 — Login redirect (`GET /auth/login`)

The user clicks "Connect to Epic Sandbox." The browser makes a `GET /auth/login` request. The server generates a cryptographically random state value, stores it in the session, then builds an Epic authorization URL with the following query parameters:

```
response_type=code
client_id=<EPIC_NONPROD_CLIENT_ID>
scope=<EPIC_SCOPE (URL-encoded)>
state=<random-state-value>
redirect_uri=<APP_REDIRECT_URI>
```

The state value is generated with `secrets.token_urlsafe(32)`, which produces 32 random bytes encoded as a URL-safe Base64 string (~43 characters). It is stored in the session under the key `oauth_state` before the redirect is issued.

The scope string is URL-encoded with `urllib.parse.urlencode`, which percent-encodes the forward slashes in SMART scope strings (e.g., `patient/Patient.read` → `patient%2FPatient.read`). Epic requires this encoding.

The server responds with a `307 Temporary Redirect` to the Epic authorization URL.

### Step 2 — Epic login and consent

The user's browser follows the redirect to Epic. The user logs in with their Epic credentials and reviews the consent screen listing the requested scopes. After approval, Epic redirects the browser back to `APP_REDIRECT_URI` with a short-lived authorization code in the query string:

```
GET /auth/callback?code=<authorization_code>
```

The authorization code expires in approximately 60 seconds. Epic also echoes the `state` value back in the callback query string:

```
GET /auth/callback?code=<authorization_code>&state=<random-state-value>
```

### Step 3 — Token exchange (`GET /auth/callback`)

The server receives the callback. Before doing anything else with the authorization code, it validates the state parameter:

1. It reads and immediately removes `oauth_state` from the session using `request.session.pop("oauth_state", None)`. Using `pop` rather than `get` is important: it makes state single-use, so the same callback cannot be replayed against a still-valid session entry.
2. It compares the retrieved value to the `state` query parameter Epic returned. If they do not match — or if `oauth_state` was not in the session at all — the request is rejected with `HTTP 400`.

Only after state validation passes does the server proceed with the authorization code. It immediately makes a back-channel `POST` directly to the Epic token endpoint — the user's browser is not involved in this step. This is what makes the Authorization Code flow more secure than the implicit flow: the access token never travels through the browser's address bar or history.

The POST body uses `client_secret_post` authentication (client credentials in the request body):

```
grant_type=authorization_code
code=<authorization_code>
redirect_uri=<APP_REDIRECT_URI>
client_id=<EPIC_NONPROD_CLIENT_ID>
client_secret=<EPIC_CLIENT_SECRET>
```

Epic responds with a JSON token payload containing `access_token`, `expires_in`, `scope`, and optionally `refresh_token`.

### Step 4 — Session storage

After a successful token exchange, the server:

1. Calls `request.session.clear()` to remove any stale data from a previous session
2. Generates a random `session_id` with `secrets.token_hex(16)`
3. Stores the full token payload in the server-side token store (`app.state.token_store[session_id]`)
4. Writes only lightweight metadata to the session cookie: `session_id`, `token_expires_at` (ISO 8601), and `scope`

The access token itself never reaches the browser. See the **Session Management** section for why.

### Step 5 — Redirect home

After storing the session, the callback handler returns a `200 OK` response with a client-side meta-refresh:

```html
<html><head><meta http-equiv="refresh" content="1;url=/"></head></html>
```

This causes the browser to land on the callback page first (storing the `Set-Cookie` header), and then navigate to `/` one second later. A `302 redirect` is not used here because some browsers (Chrome, Safari) drop `SameSite=Lax` cookies set on redirect responses that arrive at the end of a cross-site redirect chain originating from Epic's domain. Returning a `200` breaks the cross-site context before the navigation to `/` occurs.

---

## OAuth State Parameter and CSRF Protection

### What is the state parameter?

The `state` parameter is an opaque random value that the client generates at the start of an OAuth flow, sends to the authorization server, and expects to receive back unchanged in the callback. It acts as a nonce — a one-time token that binds the callback to the specific browser session that initiated the login.

RFC 6749 (the OAuth 2.0 specification), Section 10.12, explicitly recommends using `state` for CSRF protection. SMART on FHIR inherits this guidance. It is optional in the spec but considered a required best practice in any implementation that cares about security.

### What attack does it prevent?

Without state, the OAuth callback endpoint is vulnerable to a **login CSRF** attack (also called a "session fixation via OAuth" attack). The sequence looks like this:

1. An attacker initiates an OAuth flow against your app from their own browser, but does not complete the consent step. They capture the authorization URL or the callback URL with a valid `code`.
2. The attacker tricks a victim into clicking a crafted link that sends the victim's browser to your `/auth/callback` with the attacker's authorization code.
3. The victim's browser completes the callback — your server exchanges the code for a token and writes the resulting session cookie to the victim's browser.
4. The victim is now logged in, but the authenticated identity belongs to the attacker. The attacker can now access the victim's account (or, in a FHIR context, view or submit data as the victim).

This is sometimes called a "login CSRF" because the attack exploits the login endpoint rather than a form submission — the victim is coerced into logging in as someone else.

### How state prevents it

With state:

1. When the victim's browser attempts to complete the forged callback, the server checks the `state` parameter Epic echoes back against the value stored in the victim's session.
2. The victim's session contains no `oauth_state` (they never clicked "Connect to Epic") — or it contains a different value generated by a legitimate login attempt.
3. The check fails, the request is rejected with `HTTP 400`, and the forged login never completes.

State works because it is bound to the session: only the browser that initiated the flow has the matching value. An attacker operating from a separate browser cannot predict or steal the victim's session state.

### Implementation in app2

The implementation uses three standard Python building blocks:

**Generate** (in `/auth/login`):
```python
state = secrets.token_urlsafe(32)
request.session["oauth_state"] = state
```

`secrets.token_urlsafe(32)` generates 32 cryptographically random bytes and encodes them as URL-safe Base64 (~43 characters). It uses the operating system's secure random number generator (`os.urandom`), which makes the output unpredictable.

**Send** (still in `/auth/login`):
```python
params = {
    ...
    "state": state,
    ...
}
```

The state value is included in the authorization URL query string. Epic stores it and echoes it back verbatim in the callback.

**Validate and consume** (in `/auth/callback`):
```python
expected_state = request.session.pop("oauth_state", None)
if not expected_state or state != expected_state:
    raise HTTPException(status_code=400, detail="State mismatch or missing state")
```

`pop` reads the stored value and removes it from the session in a single operation. This enforces single-use: once validated, the state cannot be replayed against the same session. The comparison then catches two distinct failure modes:

- `expected_state is None` — no login flow was initiated from this session (possible replay or forged request)
- `state != expected_state` — the value Epic returned does not match what was sent (tampered or misrouted callback)

### Why this matters in a FHIR context

In a clinical application, the stakes of a successful login CSRF are higher than in a typical web app. A forged OAuth session could give an attacker access to a patient's health records, allow fraudulent FHIR write operations, or allow an attacker to impersonate a clinician. Implementing state correctly is part of SMART on FHIR's security model and should be treated as non-negotiable in any app that handles real patient data.

---

## The JWT Access Token

### What the token endpoint returns

After a successful token exchange, Epic's token endpoint responds with a JSON object:

```json
{
  "access_token": "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCIsImtpZCI6Ii4uLiJ9.eyJpc3MiOiIuLi4ifQ.SIGNATURE",
  "token_type": "Bearer",
  "expires_in": 3600,
  "scope": "openid fhirUser patient/Patient.r",
  "id_token": "eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiIuLi4ifQ.SIGNATURE"
}
```

The long dot-separated strings starting with `eyJ` are JWTs (JSON Web Tokens, pronounced "jot"). The value of `access_token` **is** the JWT — there is no separate token hidden inside the JWT that needs to be extracted. The JWT string itself is the credential that gets presented to the FHIR server on every API call.

App2 reads it directly from the response JSON:

```python
token_data = response.json()
access_token = token_data["access_token"]   # this IS the JWT string — no extraction needed
```

### JWT structure

A JWT is three Base64URL-encoded segments joined by dots:

```
<header>.<payload>.<signature>
```

**Header** — identifies the signing algorithm and key:

```json
{
  "alg": "RS256",
  "typ": "JWT",
  "kid": "<Epic signing key ID>"
}
```

**Payload** — the claims (key/value assertions) about the token and its subject:

```json
{
  "iss": "https://fhir.epic.com/interconnect-fhir-oauth/oauth2",
  "sub": "<authenticated user's Epic FHIR ID>",
  "aud": "https://fhir.epic.com/interconnect-fhir-oauth/api/FHIR/R4",
  "client_id": "<your client ID>",
  "iat": 1718000000,
  "exp": 1718003600,
  "jti": "<unique token instance ID>",
  "scope": "openid fhirUser patient/Patient.r",
  "fhirUser": "https://fhir.epic.com/.../Patient/abc123",
  "patient": "abc123"
}
```

**Signature** — a digital signature computed by Epic using its RSA private key (RS256 = RSA + SHA-256). It can be verified against Epic's public JWKS endpoint, which proves the token was issued by Epic and has not been altered in transit.

### Key claims

| Claim | Meaning |
|---|---|
| `iss` | Issuer — Epic's OAuth base URL |
| `sub` | Subject — the authenticated user's Epic internal ID |
| `aud` | Audience — who this token is intended for (the FHIR base URL) |
| `client_id` | The registered client ID of this application |
| `iat` | Issued-at time (Unix timestamp) |
| `exp` | Expiration time (Unix timestamp); Epic typically issues 1-hour tokens |
| `jti` | JWT ID — a unique identifier for this specific token instance |
| `scope` | Granted scopes (space-separated); Epic abbreviates read as `.r` and search as `.s` |
| `fhirUser` | Full FHIR URL of the authenticated user's Patient or Practitioner resource |
| `patient` | Short-form patient context ID from the launch context |

### Using the access_token for FHIR API calls

Every FHIR R4 API call must include the access_token as a **Bearer token** in the `Authorization` header:

```http
GET /interconnect-fhir-oauth/api/FHIR/R4/Patient/me HTTP/1.1
Host: fhir.epic.com
Authorization: Bearer eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9...
```

In Python with `httpx`, using the token retrieved from app2's token store:

```python
session_id = request.session.get("session_id")
token_entry = request.app.state.token_store.get(session_id, {})
access_token = token_entry.get("access_token")   # the JWT string

response = await http_client.get(
    f"{settings.epic_fhir_base_url}/Patient/me",
    headers={"Authorization": f"Bearer {access_token}"}
)
```

The Epic FHIR server receives the Bearer token, verifies its RS256 signature against Epic's JWKS endpoint, checks that it has not expired (`exp` claim), and confirms the requested resource falls within the granted `scope`. App2 never needs to decode or validate the JWT — that validation is the resource server's responsibility.

### `access_token` vs `id_token`

When the `openid` scope is included (as it is in app2's `EPIC_SCOPE`), Epic returns two JWTs in the same token response:

| Field | Type | Purpose | Intended reader |
|---|---|---|---|
| `access_token` | Bearer / access token | Authorization credential for FHIR API calls | The resource server (Epic FHIR API) |
| `id_token` | OpenID Connect identity token | Assertion about who the authenticated user is | The client application (app2) |

The distinction matters for how each token is used:

- **`access_token`**: treat as an opaque credential — forward it unchanged to the FHIR server in the `Authorization` header. The client application should not decode it or build logic that depends on its internal claim structure; only the resource server is expected to interpret it.
- **`id_token`**: meant to be decoded by the application to learn who the authenticated user is. Its payload contains standard OpenID Connect identity claims such as `sub` (Epic user ID), and optionally `name`, `email`, and `fhirUser` depending on what scopes were granted.

App2 currently stores only the `access_token`. The `id_token` is present in `token_data` but not stored. A future iteration could decode the `id_token` to display the logged-in user's name on the home page.

### Decoding a JWT for inspection

The payload segment of a JWT is Base64URL-encoded JSON — no key is required to read it. Decoding is useful for debugging and learning, but you must not rely on an unverified payload for any security decision.

**In a browser**: paste the full token at [jwt.io](https://jwt.io) to see the decoded header, payload, and signature side by side.

**In Python** (standard library only, no extra packages):

```python
import base64, json

def decode_jwt_payload(token: str) -> dict:
    payload_b64 = token.split(".")[1]
    padded = payload_b64 + "=" * (4 - len(payload_b64) % 4)
    return json.loads(base64.urlsafe_b64decode(padded))

payload = decode_jwt_payload(token_data["access_token"])
print(payload["scope"])          # space-separated granted scopes
print(payload["exp"])            # expiration as Unix timestamp
print(payload.get("fhirUser"))   # full FHIR URL of the authenticated user
```

Note: this decodes but does **not** verify the signature. For production use, verify against Epic's JWKS endpoint with a library such as `python-jose` or `PyJWT`. In app2's architecture this is not needed because the FHIR server performs that validation — app2 acts as a pass-through.

---

## Session Management

### Why a server-side token store?

Epic access tokens are JWTs, typically ~880 characters. When combined with a refresh token and other token response fields, and then JSON-serialized, base64-encoded, and signed by `itsdangerous`, the total session cookie easily exceeds the 4096-byte browser cookie size limit. Browsers silently discard oversized cookies rather than returning an error, which causes the session to disappear without any obvious indication of why.

The solution is to keep the tokens on the server and store only a short random `session_id` in the cookie:

```
Cookie: session=<signed-blob-containing-only-session_id-and-metadata>
```

The token store is an in-memory dict on `app.state`:

```python
app.state.token_store[session_id] = {
    "access_token": "...",
    "refresh_token": "...",
    "scope": "...",
}
```

When the home page (or any future FHIR route) needs to make an API call, it looks up the access token by `session_id`:

```python
session_id = request.session.get("session_id")
token_entry = request.app.state.token_store.get(session_id, {})
access_token = token_entry.get("access_token")
```

**Limitation**: `app.state.token_store` is in-memory and process-local. It is cleared on every server restart. In production, this should be replaced with Redis or another persistent store.

### Scope and Cookie Size

Even with the access token removed from the cookie, the scope string returned by Epic can cause the same overflow. When "All FHIR R4 scopes" are selected during app registration, Epic returns a scope string of approximately 5000 characters. The session cookie stores scope separately from the token store.

To avoid this:
- Request only the scopes the app actually needs via `EPIC_SCOPE` in `.env`
- Match the registered scopes in the Epic developer portal to the same minimal set

A recommended minimal scope for this bootcamp:

```
openid fhirUser launch/patient patient/Patient.read patient/Observation.read patient/Condition.read patient/MedicationRequest.read
```

Note: Epic uses abbreviated scope notation in the token response (`.r` for read, `.s` for search) regardless of how the scope was requested. The granted scope string will also reflect what the registered app is approved for, which may differ from exactly what was requested.

### Session cookie configuration

The `SessionMiddleware` is configured in `main.py`:

```python
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.session_secret_key,
    https_only=False,   # set True in production (requires HTTPS)
    same_site="lax"
)
```

`SameSite=Lax` allows the browser to send the session cookie on top-level cross-site GET navigations (needed for Epic's redirect back to the callback URL) while blocking it on cross-site subrequests.

---

## Running app2

From the project root with the virtual environment activated:

```bash
uvicorn app2.main:app --reload --port 8000
```

Then open `http://localhost:8000` in a browser.

**Important**: Always run uvicorn from the project root using dot notation (`app2.main:app`). Running it from inside the `app2/` directory will break the relative path resolution for templates and static files, and will also break the `.env` file lookup in `config.py`.

---

## Lifespan and `app.state`

### What is the lifespan context manager?

FastAPI provides a `lifespan` parameter that accepts a context manager function. That function runs once when the server starts and once when it shuts down — it is the correct place to create and tear down application-level resources like HTTP clients, database connection pools, and in-memory stores.

In app2 (`app2/main.py`):

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
import httpx
from fastapi.templating import Jinja2Templates
from pathlib import Path

@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.http_client = httpx.AsyncClient()
    app.state.templates = Jinja2Templates(directory=Path(__file__).parent / "templates")
    app.state.token_store = {}

    yield

    await app.state.http_client.aclose()

app = FastAPI(..., lifespan=lifespan)
```

### `@asynccontextmanager`

`asynccontextmanager` is a decorator from Python's standard library `contextlib` module. It transforms an `async` generator function — one that contains a `yield` — into an asynchronous context manager. FastAPI calls it internally as `async with lifespan(app)`, so you never write that yourself; you just pass the function to `FastAPI(lifespan=...)`.

Without the decorator, a generator function is just a generator. The decorator is what gives it the `__aenter__` / `__aexit__` protocol that FastAPI knows how to call.

### The `yield` — startup vs. shutdown

The `yield` statement is the dividing line between two phases:

| Phase | When it runs | Code location |
|---|---|---|
| **Startup** | Once, when the server process starts (before the first request) | Everything **before** `yield` |
| **Running** | Indefinitely, while the server handles requests | At the `yield` itself — the server is paused here |
| **Shutdown** | Once, when the server receives a stop signal (SIGTERM / Ctrl-C) | Everything **after** `yield` |

This is the same pattern as a `with` block: the `yield` is where control passes to the body of the `with` statement. In the lifespan case, the "body" is the server's entire request-handling loop.

The shutdown block in app2 contains one line:

```python
await app.state.http_client.aclose()
```

This tells `httpx` to close all open TCP connections and release socket file descriptors before the process exits. Without it, connections would be abandoned on shutdown — not a problem in development, but sloppy in production.

### Why not just initialize at module level?

It is tempting to create these objects as module-level globals in `main.py`:

```python
# This works, but it's worse
http_client = httpx.AsyncClient()
templates = Jinja2Templates(...)
```

Three reasons lifespan is better:

1. **Event loop timing.** `httpx.AsyncClient` is an async resource that must be created inside a running event loop. At module import time, no event loop exists yet. Lifespan runs after uvicorn starts the event loop, so the client is created in the right context.
2. **Guaranteed cleanup.** The code after `yield` is called even if the server exits due to an unhandled exception. Module-level globals have no cleanup hook.
3. **Scoping.** Attaching resources to `app.state` makes them an explicit part of the application instance rather than floating module-level state. This matters when running tests that create multiple `app` instances in the same process.

### `app.state` — the application-level namespace

`app.state` is a `starlette.datastructures.State` object — a simple namespace (think `types.SimpleNamespace`) that Starlette attaches to every FastAPI application instance. You can set any attribute on it:

```python
app.state.anything = some_value
```

It is not a dict. You access values with dot notation, not subscript:

```python
app.state.token_store       # correct
app.state["token_store"]    # AttributeError
```

There is no schema or type enforcement — it is intentionally a flexible bag for application-level resources. The convention is to set everything during startup and treat the values as read-only after that (with the obvious exception of mutable objects like `token_store`, whose contents change with every OAuth login).

### The three resources in app2

**`app.state.http_client`** — `httpx.AsyncClient()`

An async HTTP client used for all outbound HTTP calls to Epic: the back-channel token exchange POST to Epic's token endpoint, and every FHIR API call made from the portal. It is shared across all requests so that the underlying TCP connection pool is reused (HTTP keep-alive). Creating a new `AsyncClient` per request would open and close a new connection to Epic each time — wasteful and slower. The shutdown phase calls `.aclose()` to drain and release those connections.

**`app.state.templates`** — `Jinja2Templates(directory=Path(__file__).parent / "templates")`

A Jinja2Templates instance that loads HTML templates from the `app2/templates/` directory. The directory is resolved with `Path(__file__).parent`, which gives an absolute path relative to `main.py` regardless of what directory uvicorn was invoked from. This is more robust than a relative string like `"app2/templates"`, which would break if the working directory changed.

Note: `app2/routers/pages.py` also has a module-level `templates = Jinja2Templates(directory="app2/templates")` that is used by the `/patient` route. That instance uses a relative path and works only when uvicorn is run from the project root. The home route (`/`) uses the lifespan-initialized `request.app.state.templates` instead. This inconsistency exists in the current code; ideally all template rendering would use the same instance.

**`app.state.token_store`** — `{}`

An in-memory Python dict keyed by `session_id` (a random hex string generated at login). It stores the full token payload — including the `access_token` JWT — received from Epic's token endpoint. Keeping the token here rather than in the session cookie is what allows the cookie to stay small. See the **Session Management** section for full details.

### How route handlers access `app.state`

Every FastAPI route handler receives a `Request` object. The `Request` object holds a reference back to the application instance via `request.app`. From there, any `app.state` attribute is reachable:

```python
# In any route handler:
async def some_route(request: Request):
    token_store = request.app.state.token_store
    http_client = request.app.state.http_client
```

In app2 this pattern appears in several places:

```python
# pages.py — home route renders template from lifespan-initialized instance
return request.app.state.templates.TemplateResponse(request, "home.html", {...})

# auth.py — callback route does back-channel token exchange
response = await request.app.state.http_client.post(settings.epic_token_url, data={...})

# auth.py — callback route stores token after exchange
request.app.state.token_store[session_id] = token_data

# auth.py — logout route removes token from store
request.app.state.token_store.pop(session_id, None)

# pages.py — FHIR route calls Epic API using shared client
response = await request.app.state.http_client.get(f"{settings.epic_fhir_base_url}/Patient", headers={...})

# pages.py — FHIR route retrieves access token from store
token_entry = request.app.state.token_store.get(session_id, {})
```

The chain `request → request.app → request.app.state → request.app.state.<resource>` is the standard FastAPI/Starlette idiom for sharing application-level state with route handlers without resorting to global variables.

---

## Initial Page State

When you open `http://localhost:8000` in a browser with no active session, the home page renders its unauthenticated state. The page displays a single card with the heading **"Epic Sandbox Integration"**, a brief prompt ("Connect your Epic Sandbox account to authorize this application and begin accessing patient data."), and a **"Connect to Epic Sandbox"** button.

Clicking that button sends the browser to `GET /auth/login`, which is the entry point for the OAuth 2.0 Authorization Code flow described in the section above.

The home page template (`app2/templates/home.html`) is a single Jinja2 template that handles both states with a conditional block:

- **No active session** (`session_active` is falsy): renders the landing prompt and button.
- **Active session** (`session_active` is truthy): renders session metadata (expiration time, granted scopes, and a note that the access token is stored server-side) along with Disconnect, ID Token, and Portal buttons.

The `session_active` flag is set by the `GET /` route handler in `app2/routers/pages.py`, which checks whether a valid `session_id` is present in the signed session cookie.

---

## Patient Portal

### Template inheritance: `portal.html` and `patient.html`

The portal is built with Jinja2 template inheritance. `portal.html` is the **base layout** — it contains the common HTML structure, HTMX script tag, and CSS links that every portal page shares. Child templates extend it using `{% extends "portal.html" %}` and fill two named blocks:

- `{% block actions %}` — the section between the two `<hr>` tags, intended for action buttons
- `{% block content %}` — inside `<main>`, below the second `<hr>`, intended for results

`patient.html` is the first child template. It fills `{% block actions %}` with the "GET /Patient" button wired to HTMX, and fills `{% block content %}` with `<div id="result"></div>` — the HTMX injection target.

New portal pages for additional FHIR resources follow the same pattern: create a new child template that extends `portal.html` and fills both blocks.

### A note on Jinja2 comments in base templates

The `portal.html` header comment uses `{# ... #}` (a Jinja2 block comment) rather than `<!-- ... -->` (an HTML comment). This is required because Jinja2 evaluates `{% block %}` and `{% extends %}` tags **before** HTML is parsed. Any block tag written inside an HTML comment is still executed by Jinja2 and causes a `TemplateSyntaxError`. Jinja2 block comments strip their content before any further processing, so block tags inside them are never evaluated.

One additional subtlety: Jinja2 block comments cannot be nested, and the closing delimiter `#}` cannot be escaped. If the comment text itself contains a literal `#}` sequence (for example, in a code example showing Jinja2 comment syntax), the parser treats that as the end of the comment and evaluates everything after it as live template code. The `portal.html` header comment avoids writing the literal Jinja2 closing delimiters for this reason.

### Routes: `/patient` and `/fhir/patient`

Two routes in `app2/routers/pages.py` serve the portal:

**`GET /patient`** — a standard page route. Renders `patient.html` with the `title` variable. The route handler does no session checking; the page renders regardless of login state. The HTMX button will display an error fragment in `#result` if no session is active.

**`GET /fhir/patient`** — an HTMX endpoint. This is **not** a page route. It returns a small HTML fragment that HTMX injects into `#result`. It is called by the browser's HTMX runtime when the button is clicked, not by direct browser navigation. The route is marked `include_in_schema=False` so it is excluded from the FastAPI auto-generated API docs.

### How HTMX connects the button to the server

The "GET /Patient" button in `patient.html` carries four HTMX attributes:

```html
<button class="btn"
        hx-get="/fhir/patient"
        hx-target="#result"
        hx-swap="innerHTML"
        hx-indicator="#fhir-loading"
        hx-disabled-elt="this">
  GET /Patient
</button>
```

| Attribute | Effect |
|---|---|
| `hx-get="/fhir/patient"` | On click, HTMX sends `GET /fhir/patient` to the FastAPI server |
| `hx-target="#result"` | The server's HTML response is injected into the element with `id="result"` |
| `hx-swap="innerHTML"` | The inner content of `#result` is replaced (the `<div>` itself stays) |
| `hx-indicator="#fhir-loading"` | The loading span fades in while the request is in flight |
| `hx-disabled-elt="this"` | The button is disabled for the duration of the request to prevent double-clicks |

No page navigation occurs. The browser address bar does not change. The session cookie is sent automatically with the HTMX request because HTMX issues a same-origin HTTP GET like any other browser request.

### The FHIR request flow in `fhir_get_patient`

The route handler in `pages.py` follows six steps before returning a response.

**Step 1 — Read the session ID**

```python
session_id = request.session.get("session_id")
```

`SessionMiddleware` decodes the signed session cookie and populates `request.session` before the handler runs. If no `session_id` is present the user has no active login; an error fragment is returned immediately.

**Step 2 — Look up the access token**

```python
token_entry = request.app.state.token_store.get(session_id, {})
access_token = token_entry.get("access_token")
```

The access token is never in the session cookie — it lives in `app.state.token_store`, keyed by `session_id`. If the entry is absent (the server restarted and cleared in-memory state while the browser retained its old cookie) an error fragment is returned.

**Step 3 — Check token expiry**

```python
expires_at = datetime.fromisoformat(request.session.get("token_expires_at"))
if datetime.now(timezone.utc) >= expires_at:
    return _error_html("Access token has expired...")
```

`token_expires_at` was stored in the session cookie as an ISO 8601 string during `/auth/callback`. Checking it before making the FHIR call avoids sending a request that Epic will reject with a 401.

**Step 4 — Call Epic FHIR with the Bearer token**

```python
response = await request.app.state.http_client.get(
    f"{settings.epic_fhir_base_url}/Patient",
    headers={
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/fhir+json",
    },
)
```

The `Authorization: Bearer <token>` header is the only credential Epic needs. Epic's FHIR server validates the JWT signature, checks the `exp` claim, and confirms the request scope. The call uses `app.state.http_client` (the shared `AsyncClient` from the lifespan) so the underlying TCP connection to Epic is reused.

`Accept: application/fhir+json` is the correct MIME type per the FHIR R4 specification. Epic also honors `application/json`, but the FHIR type is preferred and may affect content negotiation for future endpoints.

**Step 5 — Handle non-2xx responses**

```python
if not response.is_success:
    return _error_html(
        f"Epic FHIR returned HTTP {response.status_code}.",
        detail=response.text,
    )
```

A non-2xx status from Epic (401, 403, 404, etc.) is caught here and returned as an error fragment. The raw response body is included as the `detail` argument, which helps diagnose scope or authorization issues during development.

**Step 6 — Format and return the JSON fragment**

```python
formatted_json = json.dumps(response.json(), indent=2)
return HTMLResponse(content=f'<pre class="fhir-json">{formatted_json}</pre>')
```

`json.dumps(indent=2)` pretty-prints the FHIR Bundle. The result is wrapped in `<pre class="fhir-json">`, which the CSS renders as a dark scrollable code block. HTMX injects this fragment into `#result` on the portal page.

### Network error handling (`httpx.TransportError`)

Both the token exchange in `auth.py` and the FHIR call in `pages.py` wrap their `httpx` calls in `try/except httpx.TransportError`:

```python
try:
    response = await http_client.post(...)   # or .get(...)
except httpx.TransportError as exc:
    # auth.py raises HTTPException; pages.py returns _error_html()
    ...
```

`httpx.TransportError` is the base class for all network-level failures:

| Subclass | Cause |
|---|---|
| `ReadError` | Connection reset by the server mid-response |
| `ConnectError` | Connection refused or DNS failure |
| `ReadTimeout` | No response received within the timeout window |
| `WriteError` | Error sending the request body |

Without this guard, any of these exceptions propagates uncaught through the middleware stack and becomes an unhandled 500. With it, the token exchange returns HTTP 502 with a readable message, and the FHIR call returns an error fragment inside `#result`.

A common trigger in development is a **stale pooled connection**: the shared `AsyncClient` keeps a pool of keepalive TCP connections to Epic's servers. If a connection has been idle long enough for Epic to close it server-side, the next request to reuse that connection receives a `ReadError` when it tries to read the response headers. Retrying (clicking the button again, or re-initiating the OAuth flow) opens a fresh connection and typically succeeds immediately.

### The `_error_html` helper

```python
def _error_html(message: str, detail: str = "") -> HTMLResponse:
    detail_block = f'<pre class="fhir-error-detail">{detail}</pre>' if detail else ""
    return HTMLResponse(content=f'<p class="fhir-error">{message}</p>{detail_block}')
```

All error paths in `fhir_get_patient` return through this helper. It produces a styled HTML fragment rather than a JSON error body or a full error page, so HTMX can inject it directly into `#result`. The optional `detail` argument adds a second block containing raw response text — shown when Epic returns a non-2xx status code with a body describing the problem.

---

## Key Routes

| Method | Path | Description |
|---|---|---|
| `GET` | `/` | Home page — shows session status or login prompt |
| `GET` | `/auth/login` | Builds Epic authorization URL and redirects |
| `GET` | `/auth/callback` | Receives authorization code; exchanges for token; sets session |
| `GET` | `/auth/logout` | Clears session cookie and removes server-side token entry |
| `GET` | `/patient` | Patient portal page — renders the HTMX-wired portal UI |
| `GET` | `/fhir/patient` | HTMX endpoint — calls Epic FHIR `GET /Patient`; returns HTML fragment |
| `GET` | `/health` | System health check — returns app name, version, environment |

---

## `__init__.py`

`app2/__init__.py` must exist (it can be empty) for Python to treat `app2` as a package. Without it, the `uvicorn app2.main:app` invocation from the project root will fail with a `ModuleNotFoundError`.

---

## OCI Deployment Notes

The deployment approach mirrors the local setup: lift-and-shift to an OCI VM running the same uvicorn process.

Changes required for production:

- Set `https_only=True` in `SessionMiddleware` (requires HTTPS termination at a reverse proxy such as nginx)
- Set a strong `SESSION_SECRET_KEY` in the production environment (not in `.env` committed to git)
- Replace `app.state.token_store` (in-memory dict) with Redis or another persistent store so sessions survive server restarts and work across multiple workers
- Run uvicorn behind a process manager (e.g., systemd or supervisor) rather than with `--reload`
- Set `APP_REDIRECT_URI` to the production HTTPS callback URL and update it in the Epic app registration
