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

---

## Directory Structure

```
app2/
├── __init__.py             # Required for dot-notation uvicorn invocation
├── config.py               # Pydantic Settings — reads from root .env
├── main.py                 # FastAPI app: lifespan, middleware, router registration
├── routers/
│   ├── auth.py             # OAuth routes: /auth/login, /auth/callback, /auth/logout
│   └── pages.py            # UI routes: / (home page)
├── static/
│   ├── css/main.css
│   └── image/favicon-fhir-72.ico
└── templates/
    └── home.html           # Jinja2 template: landing / session status page
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
EPIC_SCOPE=openid fhirUser launch/patient patient/Patient.read patient/Observation.read patient/Condition.read patient/MedicationRequest.read
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

App2 implements the standard SMART on FHIR Authorization Code flow. The steps below describe what happens at runtime.

### Step 1 — Login redirect (`GET /auth/login`)

The user clicks "Connect to Epic Sandbox." The browser makes a `GET /auth/login` request. The server builds an Epic authorization URL with the following query parameters:

```
response_type=code
client_id=<EPIC_NONPROD_CLIENT_ID>
scope=<EPIC_SCOPE (URL-encoded)>
redirect_uri=<APP_REDIRECT_URI>
```

The scope string is URL-encoded with `urllib.parse.urlencode`, which percent-encodes the forward slashes in SMART scope strings (e.g., `patient/Patient.read` → `patient%2FPatient.read`). Epic requires this encoding.

The server responds with a `307 Temporary Redirect` to the Epic authorization URL.

### Step 2 — Epic login and consent

The user's browser follows the redirect to Epic. The user logs in with their Epic credentials and reviews the consent screen listing the requested scopes. After approval, Epic redirects the browser back to `APP_REDIRECT_URI` with a short-lived authorization code in the query string:

```
GET /auth/callback?code=<authorization_code>
```

The authorization code expires in approximately 60 seconds.

### Step 3 — Token exchange (`GET /auth/callback`)

The server receives the callback. It immediately makes a back-channel `POST` directly to the Epic token endpoint — the user's browser is not involved in this step. This is what makes the Authorization Code flow more secure than the implicit flow: the access token never travels through the browser's address bar or history.

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

## Key Routes

| Method | Path | Description |
|---|---|---|
| `GET` | `/` | Home page — shows session status or login prompt |
| `GET` | `/auth/login` | Builds Epic authorization URL and redirects |
| `GET` | `/auth/callback` | Receives authorization code; exchanges for token; sets session |
| `GET` | `/auth/logout` | Clears session cookie and removes server-side token entry |
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
