# App2 — SMART Patient App on Epic

app2 is a server-side rendered FastAPI web application that authenticates users against the Epic Sandbox via the **SMART on FHIR OAuth 2.0 Authorization Code flow**. After login, it holds an access token that can be used to make FHIR R4 API calls on behalf of the authenticated user. The UI is built with Jinja2 templates and plain CSS; no JavaScript framework is used.

---

## What app2 Does

- Presents a landing page with a "Connect to Epic Sandbox" button
- Redirects the user to Epic's login/consent page (OAuth 2.0 authorization)
- Receives the authorization code callback from Epic
- Exchanges the code for an access token via a server-to-server POST (back-channel)
- Stores the access token server-side; places only a lightweight session cookie in the browser
- Displays session status (active/expired), token expiration time, and granted scopes on the home page
- Decodes the OIDC ID token server-side and presents its identity claims in a browser modal (ID Token button)
- Supports logout (clears session cookie and removes server-side token)
- Provides a patient portal page with HTMX-wired buttons that call Epic FHIR R4 endpoints: `GET /Patient`, `GET /MedicationRequest`, `GET /Observation` (lab reports), and `GET /Observation` (vital signs)

---

## Directory Structure

```
app2/
├── __init__.py             # Required for dot-notation uvicorn invocation
├── config.py               # Pydantic Settings — reads from root .env
├── main.py                 # FastAPI app: lifespan, middleware, router registration
├── routers/
│   ├── auth.py             # OAuth routes: /auth/login, /auth/callback, /auth/logout
│   └── pages.py            # UI routes: / (home), /patient, /fhir/patient, /fhir/medication
├── services/
│   └── patient_service.py  # Standalone synchronous service module (CLI/experimental use)
├── static/
│   ├── css/main.css
│   └── image/
│       ├── epic-sandbox-logo.png
│       └── favicon-fhir-72.ico
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

## Tech Stack: Architecture and Integration

### The Server-Side Rendering Paradigm

App2 is a **server-side rendered (SSR)** application: every HTML page and every HTMX fragment is assembled in Python from a Jinja2 template before being sent to the browser. The browser receives finished HTML — not a JavaScript bundle that builds the page after download, and not JSON data that client-side code must transform into markup.

This is the inverse of a single-page application (SPA):

| | SSR with HTMX (app2) | SPA (React, Vue, Svelte) |
|---|---|---|
| **Who renders HTML** | Server (Python + Jinja2) | Client (JavaScript) |
| **What travels over the wire** | Complete HTML pages or HTML fragments | JSON data |
| **Page transitions** | Full navigations or HTMX partial swaps | Client-side routing (no reload) |
| **JavaScript required** | Minimal — HTMX is a single script tag | Large bundle required |
| **Backend role** | Render HTML + call external APIs | Data API only |
| **Logic lives in** | Python (testable, typed) | JavaScript (two runtimes to reason about) |
| **Complexity budget** | Mostly in Python | Mostly in JavaScript |

HTMX sits between full-page SSR and SPA: the server still produces HTML (SSR's strength), but HTMX injects that HTML into a specific part of the current page rather than triggering a full navigation. The user gets the interactive feel of a SPA without the client-side complexity.

### Request Lifecycle: How the Layers Collaborate

A complete interaction through app2 touches all four major components. Here is the full sequence when a logged-in user clicks "GET /Patient" on the portal page:

```
Browser (HTMX)
  │
  │  1. HTMX intercepts the button click.
  │     Issues: GET /fhir/patient
  │     With:   session cookie (same-origin, sent automatically)
  │
  ▼
FastAPI + Starlette (uvicorn)
  │
  │  2. SessionMiddleware decodes the signed cookie on the way in.
  │     Populates request.session with the cookie's payload dict.
  │
  │  3. Router matches GET /fhir/patient → fhir_get_patient() handler.
  │
  │  4. Handler reads session_id from request.session.
  │     Looks up access_token from request.app.state.token_store.
  │
  │  5. Handler calls Epic FHIR using the shared AsyncClient.
  │     Control yields (await) — event loop can serve other requests during the wait.
  │
  ▼
HTTPX AsyncClient  →  Epic FHIR Server
  │
  │  6. Sends: GET /FHIR/R4/Patient
  │     With:  Authorization: Bearer <access_token>
  │            Accept: application/fhir+json
  │
  │  7. Epic validates the JWT, checks granted scope, returns a FHIR Bundle.
  │
  │  8. HTTPX delivers the response object back to the handler.
  │
  ▼
FastAPI handler
  │
  │  9. json.dumps(response.json(), indent=2) — pretty-print the Bundle.
  │     Returns: HTMLResponse('<pre class="fhir-json">...</pre>')
  │
  │  10. SessionMiddleware re-serializes request.session on the way out
  │      and sets the updated Set-Cookie header (if session changed).
  │
  ▼
Browser (HTMX)
  │
  │  11. HTMX receives the HTML fragment (<pre>…</pre>).
  │      Injects it into #result using innerHTML swap.
  │      No navigation. No page reload. Address bar unchanged.
  │
  ▼
  Page updates in place.
```

The browser never sees the access token, never receives raw JSON, and does not write a line of rendering code. All logic is in Python. The browser's job is to display the HTML that arrives.

---

### FastAPI

#### Async-first design

FastAPI is built on [Starlette](https://www.starlette.io/) and the ASGI (Asynchronous Server Gateway Interface) standard. Every route handler in app2 is declared `async def`, allowing uvicorn to serve other requests while waiting for I/O — specifically, the outbound HTTPS calls to Epic:

```python
async def fhir_get_patient(request: Request):
    response = await request.app.state.http_client.get(...)
    #                  ^^^^^ suspends here during Epic's response time (~100–500 ms)
    ...
```

The `await` keyword yields control back to the event loop during the network wait. A synchronous framework (Flask, Django without async views) would block the entire process during that wait. An ASGI app continues handling other requests in the meantime.

**The rule**: if a function contains `await`, it must be `async def`. If a function calls another `async def` function, it too must be `async def`. Async propagates upward through the call stack — you cannot `await` inside a non-async function. Never call `await` in a regular function; Python raises `SyntaxError`.

For CPU-bound work (heavy computation, not I/O) inside an async handler, use `asyncio.to_thread()` to delegate to a thread pool rather than blocking the event loop directly:

```python
import asyncio
result = await asyncio.to_thread(some_blocking_function, arg1, arg2)
```

#### APIRouter and application assembly

`main.py` is intentionally thin. It creates the `FastAPI` instance, registers middleware, and mounts routers. Route handlers live in the `routers/` modules:

```python
# main.py
app.include_router(auth_router, prefix="/auth")   # all routes in auth.py get /auth prefix
app.include_router(pages_router)                  # pages.py routes are unprefixed
```

The `prefix` parameter prepends to every route defined in the router. A route declared `@router.get("/login")` in `auth.py` becomes `/auth/login` in the full application. Routes in `pages.py` use no prefix, so `@router.get("/")` stays `/`.

This pattern scales cleanly: add a new module to `routers/`, define routes within it, call `include_router` once in `main.py`. Each router is independently readable and testable without knowledge of the others.

#### The `Request` object as the integration point

Virtually every route handler in app2 accepts a `Request` parameter. `Request` is the primary integration point — the gateway to everything that crosses the HTTP boundary and to application-level state:

```python
request.session           # dict-like: decoded/signed session cookie payload
request.app               # the FastAPI application instance
request.app.state         # State namespace set up in lifespan (token_store, http_client, etc.)
request.query_params      # URL query string params (e.g., ?code=... from Epic callback)
request.headers           # incoming HTTP headers
request.url_for("name")   # reverse URL lookup by route name — generates absolute URLs
```

Understanding `Request` is the key to reading app2's handlers: they read inputs from `request.session` and `request.query_params`, retrieve resources from `request.app.state`, and delegate outbound HTTP to `request.app.state.http_client`.

`request.app` is particularly important in modular apps: routers do not import `app` directly (that would create a circular import). Instead, any handler in any router can access the application via `request.app`. This is why `app.state.token_store` is reachable from `auth.py`, `pages.py`, or any future router without any import dependencies between them.

#### Middleware and the request/response pipeline

Middleware wraps every request/response cycle. In app2, `SessionMiddleware` is the only middleware:

```python
app.add_middleware(SessionMiddleware, secret_key=..., https_only=False, same_site="lax")
```

`SessionMiddleware` performs two operations automatically on every request:

**Inbound**: reads the `session` cookie, verifies the `itsdangerous` HMAC signature, decodes the JSON payload into a Python dict, and attaches it to the request as `request.session`. If the cookie is absent, tampered with, or expired, `request.session` is an empty dict.

**Outbound**: after the handler returns, `SessionMiddleware` serializes `request.session` back to JSON, signs it, and sets the `Set-Cookie` header on the response. Any mutation the handler makes to `request.session` is automatically persisted — no explicit "save session" call is needed.

Multiple middleware can be stacked with multiple `add_middleware` calls. They execute in reverse registration order (last registered runs outermost). For app2's single middleware the order doesn't matter, but this is worth knowing when adding logging, CORS, or rate-limiting middleware later.

#### `response_class` and `include_in_schema`

Two decorator kwargs appear throughout app2's routes and are worth understanding:

```python
@router.get("/fhir/patient", response_class=HTMLResponse, include_in_schema=False)
```

**`response_class=HTMLResponse`**: FastAPI's default response type is `JSONResponse` (Content-Type: `application/json`). Specifying `HTMLResponse` changes the default to `Content-Type: text/html`. Route handlers that return `HTMLResponse(content=...)` directly would work without this, but the decorator-level declaration also affects FastAPI's OpenAPI schema generation and makes intent clear.

**`include_in_schema=False`**: excludes the route from FastAPI's auto-generated OpenAPI documentation (accessible at `/docs`). Use this for internal endpoints that are UI implementation details — HTMX fragment endpoints, internal redirect handlers, and similar. It keeps the public API surface clean and signals to future developers that these routes are not intended as a stable external contract.

---

### HTMX

#### The hypermedia model

HTMX's philosophical foundation comes from [Roy Fielding's REST constraints](https://www.ics.uci.edu/~fielding/pubs/dissertation/rest_arch_style.htm) — specifically **hypermedia as the engine of application state** (HATEOAS). The core idea: HTML with its links and forms already describes what the user can do next. A web application doesn't need JavaScript to dynamically update the page; it needs a way to ask the server for new HTML and insert it.

HTMX extends HTML elements with new attributes that enable HTTP requests and DOM updates without writing JavaScript. The philosophical consequence: **HTMX endpoints must return HTML, not JSON.**

```python
# Wrong for HTMX — the browser receives JSON and renders it as raw text
return JSONResponse({"status": "ok", "data": patient_bundle})

# Right for HTMX — the browser injects the HTML directly into #result
return HTMLResponse(content=f'<pre class="fhir-json">{formatted_json}</pre>')
```

This is a fundamental mindset shift from API-first thinking. In an HTMX application, the server is not a data provider; it is an HTML renderer. The server decides what the user sees by choosing what HTML to return. The browser's only job is to put it somewhere.

#### HTMX attribute vocabulary

The five attributes in app2 cover the most common patterns:

| Attribute | Purpose | Default behavior |
|---|---|---|
| `hx-get` / `hx-post` / `hx-put` / `hx-delete` | HTTP method and URL to call | (required — no default) |
| `hx-target` | CSS selector for the element to update | The element that triggered the request |
| `hx-swap` | How to insert the response into the target | `innerHTML` |
| `hx-indicator` | CSS selector for a loading indicator | None |
| `hx-disabled-elt` | Elements to disable during the request | None |

Beyond these, the HTMX attribute library includes:

| Attribute | Use case |
|---|---|
| `hx-trigger` | Control when the request fires — `click` (default for buttons), `change`, `keyup delay:500ms`, `intersect` (on scroll into view), `every 2s` (polling) |
| `hx-push-url` | Update the browser's address bar without navigation |
| `hx-boost` | Upgrade all `<a>` and `<form>` elements in a subtree to HTMX requests automatically |
| `hx-confirm` | Show a browser confirm dialog before issuing the request |
| `hx-vals` | Include additional values in the request body |
| `hx-headers` | Include additional HTTP headers with the request |
| `hx-on:htmx:response-error` | Override HTMX's handling of non-2xx responses |

#### Swap strategies

`hx-swap` controls how the response HTML is placed relative to the target element:

| Value | Effect |
|---|---|
| `innerHTML` | Replace the target's inner content (the target element itself remains) |
| `outerHTML` | Replace the entire target element including the element itself |
| `beforebegin` | Insert before the target element in the DOM |
| `afterbegin` | Insert as the first child of the target |
| `beforeend` | Append as the last child of the target — ideal for infinite scroll, append-only activity feeds |
| `afterend` | Insert after the target element |
| `delete` | Remove the target from the DOM (response content is ignored) |
| `none` | Do not modify the DOM — useful when the request has a side effect and a separate `hx-trigger` handles the refresh |

App2 uses `innerHTML` for all current endpoints. `beforeend` is the one to reach for when building a list that accumulates entries across multiple HTMX calls.

#### Loading indicators

HTMX adds the CSS class `htmx-request` to the element initiating a request while the request is in flight. `hx-indicator` designates a separate element that HTMX reveals during this time by transitioning its opacity:

```html
<!-- Button: HTMX adds htmx-request class while request is in flight -->
<button hx-get="/fhir/patient" hx-indicator="#fhir-loading" ...>GET /Patient</button>

<!-- Indicator: hidden by default via .htmx-indicator CSS; shown when parent has htmx-request -->
<span id="fhir-loading" class="htmx-indicator fhir-loading">Loading&hellip;</span>
```

The `.htmx-indicator` class sets `opacity: 0` and `transition: opacity 200ms` by default (from the HTMX CDN script). No JavaScript animation code is needed — HTMX and CSS handle the entire interaction.

#### Non-2xx responses and error HTML

HTMX does **not** swap the response body into the target when the server returns a 4xx or 5xx status code. By default it fires an `htmx:responseError` event and leaves the page unchanged. This means HTMX endpoints that encounter errors should return `HTTP 200` with a styled error HTML fragment:

```python
# Wrong: HTMX ignores this response body; #result stays unchanged
return HTMLResponse(content="<p>Something failed.</p>", status_code=400)

# Right: HTMX swaps the error HTML into #result
return _error_html("Something failed.")  # returns HTMLResponse with status 200
```

This is why `_error_html` exists in `pages.py` and why every error path returns through it. The user sees the error message in context; no full-page reload or redirect is needed.

(HTMX's non-2xx behavior can be overridden with `hx-on:htmx:response-error`, but returning error HTML at 200 is simpler and more predictable.)

#### When HTMX is — and isn't — the right tool

HTMX is a strong choice when:
- UI interactions map cleanly to server round-trips: button click → server call → DOM update
- The team wants to stay in Python and avoid a JavaScript build pipeline
- State lives on the server and the UI is a view over it
- Interactions are relatively simple: show/hide, append results, submit forms

HTMX is less ideal when:
- Rich client-side state is required (complex multi-step forms with local validation, drag-and-drop editors, real-time collaborative canvases)
- Sub-100ms response times are critical for perceived performance — every HTMX interaction is a round-trip to the server
- Offline support or progressive web app features are needed
- The team is already invested in a JavaScript framework

For this bootcamp's FHIR API explorer pattern — click a button, get data from a server, display it — HTMX is a near-perfect fit.

---

### Jinja2 Templates

#### The context dict: the Python-to-HTML boundary

The context dict passed to `TemplateResponse` is the only bridge between Python and the template. Every variable the template references must be explicitly included:

```python
return request.app.state.templates.TemplateResponse(
    request,
    "home.html",
    {
        "session_active": session_active,       # bool
        "expires_display": expires_display,     # str (pre-formatted for display)
        "id_token_claims_json": ...,            # str | None (pre-formatted JSON)
    },
)
```

Variables absent from the dict raise `UndefinedError` at render time (or silently produce empty strings with lax undefined settings). FastAPI's `TemplateResponse` automatically adds `request` to the context, which is why `{{ request.url_for('static', path='css/main.css') }}` works in templates without explicitly passing `request`.

**Best practice: pass pre-formatted values, not raw objects.** In app2, `id_token_claims_json` is a JSON string computed by `json.dumps(indent=2)` in Python — the template just injects it, no processing needed. `expires_display` is a formatted datetime string like `"Jun 16, 2026 at 02:30 PM UTC"` — the template does not need to know about `strftime`. This keeps templates thin and keeps logic in Python where it can be tested and type-checked.

#### Template inheritance in depth

Jinja2's template inheritance mirrors class inheritance: a base template defines the common layout and declares named override points (`{% block name %}{% endblock %}`); child templates fill in those blocks.

App2's portal hierarchy:

```
portal.html (base)
  Defines:
    {% block title %}     ← page title in <title>
    {% block actions %}   ← FHIR action buttons between the <hr> tags
    {% block content %}   ← main result area below the second <hr>

patient.html (child)
  {% extends "portal.html" %}
  Fills:
    {% block actions %}   ← GET /Patient and GET /MedicationRequest buttons
    {% block content %}   ← <div id="result"></div>
```

Key patterns for template inheritance:

**`{{ super() }}`** — renders the parent block's content before adding to it. Useful when a child should append to, not replace, the base template's block:

```html
{% block actions %}
  {{ super() }}
  <!-- additional buttons specific to this child -->
{% endblock %}
```

**Multi-level inheritance** — a grandchild template can extend a child, which extends the base. Useful when a subset of pages share a sub-layout (e.g., all admin pages share a sidebar defined in `admin_base.html`, which itself extends `portal.html`).

**Variables across blocks** — a variable defined with `{% set x = ... %}` at the template level (outside any block) is available in all blocks of that template. Variables set inside a block are local to that block.

#### Autoescaping and the `| safe` filter

Jinja2 autoescaping converts `<`, `>`, `&`, `"`, and `'` to HTML entities when rendering template variables. This is the primary built-in defense against XSS: if a user-supplied string containing `<script>alert(1)</script>` ends up in a template variable, it renders as visible text, not executable JavaScript.

The `| safe` filter bypasses autoescaping for a specific variable. Use it only when:
1. The content originates from a trusted, server-controlled source (not user input)
2. The content is intentionally HTML or pre-formatted text that must render as-is

In app2, `id_token_claims_json` is marked `| safe` because it is JSON generated by `json.dumps()` from a dict decoded from Epic's HTTPS token endpoint — no user input is in the path.

**Hard rule**: `{{ user_supplied_value | safe }}` is a security vulnerability. Never apply `| safe` to any string that originated from user input, URL parameters, or external systems that could inject malicious content.

#### Useful Jinja2 built-in filters

| Filter | Example | Effect |
|---|---|---|
| `\| default("N/A")` | `{{ value \| default("N/A") }}` | Render fallback when value is undefined or falsy |
| `\| escape` | `{{ html_string \| escape }}` | Explicitly HTML-escape (useful when autoescaping is off) |
| `\| truncate(50)` | `{{ long_text \| truncate(50) }}` | Shorten to N chars and append ellipsis |
| `\| upper` / `\| lower` | `{{ name \| upper }}` | Case conversion |
| `\| tojson` | `{{ data_dict \| tojson }}` | Serialize Python dict/list to a JSON-safe string for use in inline `<script>` tags |
| `\| join(", ")` | `{{ items \| join(", ") }}` | Join a list with a separator |
| `\| length` | `{{ items \| length }}` | Length of a sequence |
| `\| selectattr("active")` | `{{ users \| selectattr("active") }}` | Filter a list of objects by attribute truthiness |

`| tojson` is particularly useful for injecting Python data into inline JavaScript without manual serialization:

```html
<script>
  const config = {{ settings_dict | tojson }};
</script>
```

#### Comments in Jinja2 templates

Jinja2 has two comment syntaxes:

- **HTML comments** `<!-- ... -->`: visible in the browser's DevTools source view; Jinja2 still evaluates block tags inside them, which can cause `TemplateSyntaxError` when block or extends tags appear in comments.
- **Jinja2 block comments** `{# ... #}`: stripped entirely before any processing; block tags inside them are never evaluated. Use this for commenting out Jinja2 logic or for header comments in base templates that define blocks.

`portal.html` uses a `{# ... #}` block comment for its header exactly because the comment would otherwise need to reference Jinja2 block syntax.

---

### HTTPX

#### Why `httpx` instead of `requests`

`requests` is a synchronous library — it blocks the calling thread during the network wait. In an async FastAPI handler, blocking the thread means blocking the event loop, which prevents all other requests from being processed during that time:

```python
# Blocks the entire event loop — never do this in an async handler
import requests
response = requests.get(url, headers=headers)   # blocks for 300ms

# Non-blocking — suspends the handler, event loop serves other requests meanwhile
import httpx
response = await http_client.get(url, headers=headers)
```

`httpx` provides an `AsyncClient` with an API nearly identical to `requests`, so the mental model transfers directly. The only difference in usage is the `await` keyword and the declaration of the surrounding function as `async def`.

(This is why `services/patient_service.py` is marked as a CLI/experimental module — it uses `requests` synchronously, which is fine in a standalone script but wrong inside a FastAPI route handler.)

#### Connection pooling and the shared `AsyncClient`

`httpx.AsyncClient` maintains a pool of persistent TCP connections (HTTP keep-alive). Establishing a TCP + TLS connection to a remote server takes time — typically 50–200ms — due to the TCP handshake plus the TLS certificate negotiation. If a new `AsyncClient` were created for every request, that overhead would be paid every time.

The lifespan pattern creates one client at startup and reuses it across all requests:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.http_client = httpx.AsyncClient()   # one client, shared pool
    yield
    await app.state.http_client.aclose()           # drain connections on shutdown
```

Epic's servers see a persistent connection that is reused across token exchanges and FHIR calls — faster and more efficient. The `.aclose()` in the shutdown phase drains in-flight requests and releases socket file descriptors cleanly.

#### Configuring timeouts

App2 does not configure explicit timeouts on the `AsyncClient`. In development, this is acceptable — Epic's sandbox typically responds in well under a second. For production, always set a timeout:

```python
app.state.http_client = httpx.AsyncClient(
    timeout=httpx.Timeout(connect=5.0, read=30.0, write=10.0, pool=5.0)
)
```

Without timeouts, a hung Epic endpoint holds the handler open indefinitely. With many concurrent users, this eventually exhausts the event loop's capacity to handle new requests — a slow resource leak that manifests as increasing latency across the entire application.

#### Reading responses safely

The `httpx.Response` object provides several useful properties:

```python
response.status_code      # int: 200, 401, 403, 500, etc.
response.is_success       # True for 2xx status codes
response.is_client_error  # True for 4xx
response.is_server_error  # True for 5xx
response.text             # response body as str (decoded using Content-Type charset)
response.json()           # parse body as JSON → Python dict/list (raises if not valid JSON)
response.headers          # dict-like: response headers
response.content          # response body as raw bytes
```

Always check `is_success` before calling `.json()`. An error response from Epic (401, 403, etc.) may return a plain-text or XML body — calling `.json()` on it raises `json.JSONDecodeError`. The pattern in app2:

```python
if not response.is_success:
    return _error_html(f"Epic FHIR returned HTTP {response.status_code}.", detail=response.text)

formatted_json = json.dumps(response.json(), indent=2)  # safe: we know it's JSON
```

---

### Best Practices for This Stack

#### Async all the way down — no sync blocking in handlers

Every function called from an `async def` route handler that does any I/O must itself be `async def` and must be `await`ed. Mixing synchronous blocking calls (file I/O with standard `open()`, synchronous HTTP with `requests`, `time.sleep()`) into an async handler blocks the event loop and defeats the concurrency benefits of ASGI. Use async equivalents (`aiofiles`, `httpx.AsyncClient`, `asyncio.sleep`) or delegate to a thread pool via `asyncio.to_thread()`.

#### Keep route handlers thin — logic belongs in helpers

Route handlers should read inputs, call helpers, and return responses. Business logic (building FHIR query parameters, transforming response data, formatting output) belongs in helper functions or service modules. In app2, `_decode_jwt_payload` and `_error_html` are small examples of this separation. Thin handlers are easier to read, and logic in pure functions is easier to unit test independently of the HTTP layer.

#### Use `app.state` for shared resources — not module-level globals

Module-level globals in `main.py` create invisible dependencies between modules and cause problems in tests that create multiple `app` instances. `app.state` makes application-level resources explicit — they are always accessed through `request.app.state`, making the dependency visible at the call site. This also makes it straightforward to inject mocks in tests by replacing `app.state.http_client` or `app.state.token_store` before a test request.

#### Always include `hx-disabled-elt` on HTMX action buttons

Without `hx-disabled-elt="this"`, a user can click a button multiple times before the first request completes, queuing duplicate server calls. Always disable the triggering element for the duration of the request. For a button that triggers an expensive or non-idempotent operation (a write, a token exchange), this prevents duplicate submissions.

#### Store only non-sensitive metadata in the session cookie

The session cookie is signed (the signature proves it wasn't tampered with) but **not encrypted** (the payload is base64-encoded JSON, readable by anyone who has the cookie value). Store only lightweight, non-sensitive metadata in the cookie: session IDs, expiry timestamps, scope strings. Never put access tokens, secrets, or PII directly in the session. Keep sensitive data in the server-side store (`app.state.token_store` or Redis in production) and reference it by a short random ID in the cookie.

#### Scope template context to what the template needs — not more

Pass the minimal set of pre-computed values to `TemplateResponse`. Passing entire database models or complex Python objects as template context creates invisible coupling: if the object's attribute names change, the template breaks silently at render time rather than raising a Python error. Pre-format display strings (dates, currencies, truncated text) in Python and pass the result; the template should not call methods or navigate object graphs.

#### Match `include_in_schema=False` to endpoint intent consistently

Every HTMX fragment endpoint and every internal redirect handler should be `include_in_schema=False`. These are UI implementation details, not public API contracts. Keeping them out of `/docs` prevents confusion for future developers (or API clients) who might otherwise try to call them directly.

#### Use `Path(__file__).parent` for template and static paths in lifespan

Template and static file directory paths resolved relative to `main.py`'s own location are robust regardless of the working directory at runtime:

```python
Jinja2Templates(directory=Path(__file__).parent / "templates")
```

A relative string like `"app2/templates"` works only when uvicorn is invoked from the project root. The `Path(__file__).parent` form is an absolute path at runtime and works from any working directory.

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
- `EPIC_SCOPE`: In Epic's **sandbox**, this value acts as a trigger to initiate the OAuth flow rather than as a precise declaration of which resources to access. Epic grants all API capabilities registered in the developer portal regardless of which specific FHIR scopes appear in the authorization request. For sandbox development, `"openid fhirUser"` is sufficient — the actual FHIR access is controlled entirely by the app registration. **In Epic's production environment this changes**: the requested scopes must match registered capabilities and only the explicitly requested scopes are granted. See the **Epic Scope Behavior: Sandbox vs. Production** subsection below and the **Scope and Cookie Size** section for cookie size considerations.

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

### API Capabilities and Category-Specific Registration

For most FHIR resource types, enabling a single capability (e.g., MedicationRequest.Read) grants access to the entire resource. **Observation is different**: Epic registers Observation access per category. Each clinical domain is a separate capability toggle:

| Epic capability name | Category granted | Scope format in token |
|---|---|---|
| Observation.Read — Vital Signs (R4) | `vital-signs` | `patient/Observation.r?category=...observation-category\|vital-signs` |
| Observation.Read — Laboratory (R4) | `laboratory` | `patient/Observation.r?category=...observation-category\|laboratory` |
| Observation.Read — Social History (R4) | `survey` | `patient/Observation.r?category=...observation-category\|survey` |

The token response reflects this — rather than a single `patient/Observation.r`, you receive one scope entry per enabled category. Epic enforces each grant independently at the API level: a token with only the `survey` category grant will receive a 403 on a request for `category=laboratory` even though both use the same resource type.

**After enabling new capabilities in the portal**, changes typically provision within a few minutes in the sandbox. The quickest way to confirm provisioning is to log out of app2, reconnect to Epic, and check the Scope row on the home page. The new category scopes should appear in the granted scope string.

### Epic Scope Behavior: Sandbox vs. Production

This is one of the most practically important things to understand when developing against Epic's sandbox.

**In Epic's sandbox**, `EPIC_SCOPE` in `.env` is effectively a trigger for the OAuth flow. Epic grants every API capability registered in the developer portal, regardless of what specific FHIR scopes were included in the authorization request. App2 uses `EPIC_SCOPE="openid fhirUser"` — two identity scopes — and Epic's sandbox returns a token containing a dozen clinical resource scopes drawn entirely from the app registration.

The implication: adding or removing `patient/Observation.read` from `EPIC_SCOPE` has no effect in the sandbox. What controls access is the app registration. If you get a 403 on a FHIR call, the fix is in the portal, not in `EPIC_SCOPE`.

**In Epic's production environment**, behavior matches the SMART on FHIR specification. The authorization request must explicitly include each scope the app needs, and Epic only grants scopes that were both requested and registered. An app that requests `openid fhirUser` in production receives exactly those two scopes — no clinical resource access.

The practical consequence: `EPIC_SCOPE` needs no changes during sandbox development, but must be updated to enumerate all required resource scopes before deploying to production. The app registration must also be approved for production use separately from the sandbox registration.

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

The token store entry holds five fields:

```python
request.app.state.token_store[session_id] = {
    "access_token": token_data["access_token"],
    "refresh_token": token_data.get("refresh_token", ""),
    "scope": token_data.get("scope", ""),
    # id_token: OIDC identity JWT — present when openid scope is granted.
    # Decoded server-side to display identity claims in the ID Token dialog.
    "id_token": token_data.get("id_token", ""),
    # patient: FHIR ID of the in-context patient from Epic's token response.
    # Required as a search parameter for patient-specific resources such as
    # MedicationRequest (/MedicationRequest?patient=<id>). Empty string
    # when the launch was not patient-scoped.
    "patient": token_data.get("patient", ""),
}
```

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

App2 stores both tokens in the server-side token store. The `id_token` is decoded server-side at page load time and its claims are displayed in the **ID Token dialog** on the home page. See the **ID Token Dialog** section for full details.

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

## ID Token Dialog

### Overview

When the `openid` scope is granted, Epic returns an `id_token` alongside the `access_token` in the token response. The `id_token` is an OIDC JWT containing identity claims about the authenticated user — not a credential for API calls, but an assertion of who logged in. Its payload typically includes `sub` (Epic user ID), `fhirUser` (full FHIR URL of the user's resource), and `iat`/`exp` timestamps.

App2 stores the `id_token` in the server-side token store and decodes it server-side at every home page load to populate an "ID Token" button and `<dialog>` modal. Clicking the button opens the modal showing the decoded JWT payload.

### Server-side decoding in the home route

The `GET /` handler in `pages.py` retrieves the raw `id_token` JWT from the token store, decodes its payload with `_decode_jwt_payload`, and passes two template variables to `home.html`:

```python
id_token_claims = None
id_token_claims_json = None
if session_id:
    token_entry = request.app.state.token_store.get(session_id, {})
    raw_id_token = token_entry.get("id_token", "")
    if raw_id_token:
        id_token_claims = _decode_jwt_payload(raw_id_token)
        id_token_claims_json = json.dumps(id_token_claims, indent=2)
```

`id_token_claims_json` is pre-formatted JSON (pretty-printed with `indent=2`) produced on the server. The template injects it directly into a `<pre>` block without any further processing. Both variables are `None` when the session has no `id_token` (openid scope not granted, or not yet logged in), which causes the button and dialog to be omitted entirely from the rendered HTML.

### `_decode_jwt_payload`

```python
def _decode_jwt_payload(token: str) -> dict | None:
    try:
        payload_b64 = token.split(".")[1]
        padding = 4 - len(payload_b64) % 4
        payload_b64 += "=" * (padding % 4)
        return json.loads(base64.urlsafe_b64decode(payload_b64))
    except Exception:
        return None
```

A JWT's payload segment is Base64URL-encoded JSON. Base64URL omits padding characters (`=`), so the decoder must restore them before calling `urlsafe_b64decode`. The two-step modulo (`4 - len % 4`, then `% 4`) avoids adding four `=` characters when the length is already a multiple of four — adding `====` would be invalid Base64.

Signature verification is intentionally skipped. The token was received from Epic over a TLS-secured back-channel during the OAuth callback, so its authenticity is already established by the transport. This function is for display only.

The function returns `None` on any decoding failure rather than raising, so a malformed or absent `id_token` does not crash the home page — the ID Token button is simply not rendered.

### The `<dialog>` element

The modal uses the native HTML `<dialog>` element — no JavaScript library is needed:

```html
<dialog id="id-token-dialog"
        onclick="if (event.target === this) this.close()">

  <div class="dialog-header">
    <h2>OpenID Connect ID Token</h2>
    <button class="dialog-close"
            onclick="this.closest('dialog').close()"
            aria-label="Close dialog">&times;</button>
  </div>

  <div class="dialog-body">
    <p class="dialog-subtitle">
      Decoded JWT payload &mdash; identity claims returned by Epic
    </p>
    <pre class="fhir-json">{{ id_token_claims_json | safe }}</pre>
  </div>

</dialog>
```

Three ways to close the dialog:

1. **× button** — inline `onclick` calls `this.closest('dialog').close()`
2. **ESC key** — native browser behavior built into `<dialog>`, no code required
3. **Backdrop click** — the `onclick` on `<dialog>` checks `event.target === this`; a click that lands on the dialog element itself (outside the content box) closes it

The dialog is opened by the "ID Token" button in the action row:

```html
<button class="btn btn--secondary"
        onclick="document.getElementById('id-token-dialog').showModal()">
  ID Token
</button>
```

`showModal()` opens the dialog as a modal: it is centered on the page, a `::backdrop` overlay dims the background, and focus is trapped inside the dialog until it is closed. This is all handled by the browser; no CSS or JS is required beyond calling `showModal()`.

Both the button and the `<dialog>` element are wrapped in `{% if id_token_claims %}` so they are only present in the DOM when the decoded claims are available.

### The `| safe` Jinja2 filter

```html
<pre class="fhir-json">{{ id_token_claims_json | safe }}</pre>
```

Jinja2 auto-escapes HTML by default: double-quote characters in JSON become `&quot;`, making the `<pre>` block unreadable. The `| safe` filter marks the string as already safe, bypassing escaping. This is appropriate here because `id_token_claims_json` originates from Epic's HTTPS token endpoint and contains only structured claim values (strings, numbers, booleans) — not user-controlled HTML.

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
    "id_token": "...",   # OIDC identity JWT; decoded server-side for the ID Token dialog
    "patient": "...",    # Epic patient FHIR ID; required for MedicationRequest queries
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

An in-memory Python dict keyed by `session_id` (a random hex string generated at login). It stores five fields from Epic's token response: `access_token`, `refresh_token`, `scope`, `id_token` (the OIDC identity JWT, decoded server-side for the ID Token dialog), and `patient` (the FHIR patient ID, required as a search parameter for MedicationRequest). Keeping all tokens here rather than in the session cookie is what allows the cookie to stay small. See the **Session Management** section for full details.

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

The portal is built with Jinja2 template inheritance. `portal.html` is the **base layout** — it contains the common HTML structure, HTMX script tag, CSS links, and the Font Awesome icon kit CDN script that every portal page shares. Child templates extend it using `{% extends "portal.html" %}` and fill two named blocks:

- `{% block actions %}` — the section between the two `<hr>` tags, intended for action buttons
- `{% block content %}` — inside `<main>`, below the second `<hr>`, intended for results

`patient.html` is the first child template. It fills `{% block actions %}` with five HTMX-wired buttons — Patient Summary, GET /Patient, GET /MedicationRequest, GET /LabReports, and GET /VitalSigns — and fills `{% block content %}` with `<div id="result"></div>`, the HTMX injection target shared by all buttons.

New portal pages for additional FHIR resources follow the same pattern: create a new child template that extends `portal.html` and fills both blocks.

### A note on Jinja2 comments in base templates

The `portal.html` header comment uses `{# ... #}` (a Jinja2 block comment) rather than `<!-- ... -->` (an HTML comment). This is required because Jinja2 evaluates `{% block %}` and `{% extends %}` tags **before** HTML is parsed. Any block tag written inside an HTML comment is still executed by Jinja2 and causes a `TemplateSyntaxError`. Jinja2 block comments strip their content before any further processing, so block tags inside them are never evaluated.

One additional subtlety: Jinja2 block comments cannot be nested, and the closing delimiter `#}` cannot be escaped. If the comment text itself contains a literal `#}` sequence (for example, in a code example showing Jinja2 comment syntax), the parser treats that as the end of the comment and evaluates everything after it as live template code. The `portal.html` header comment avoids writing the literal Jinja2 closing delimiters for this reason.

### Routes: `/patient` and the HTMX fragment endpoints

Five routes in `app2/routers/pages.py` serve the portal:

**`GET /patient`** — a standard page route. Renders `patient.html` with the `title` variable. The route handler does no session checking; the page renders regardless of login state. The HTMX buttons will display error fragments in `#result` if no session is active.

**`GET /fhir/patient`** — HTMX endpoint; calls Epic `GET /Patient` and returns an HTML fragment.

**`GET /fhir/medication`** — HTMX endpoint; calls Epic `GET /MedicationRequest?patient=<id>` and returns an HTML fragment. See the **GET /MedicationRequest** section for full details.

**`GET /fhir/labreport`** — HTMX endpoint; calls Epic `GET /Observation?patient=<id>&category=laboratory` and returns an HTML fragment.

**`GET /fhir/vitalsigns`** — HTMX endpoint; calls Epic `GET /Observation?patient=<id>&category=vital-signs` and returns an HTML fragment.

All four fragment endpoints are marked `include_in_schema=False` — they are excluded from FastAPI's auto-generated API docs at `/docs`. See the **GET /Observation** section for full details on the lab and vital signs endpoints.

### How HTMX connects the buttons to the server

All action buttons in `patient.html` use the same five HTMX attributes, differing only in `hx-get`. The full button set as currently implemented:

```html
<!-- Featured shortcut — styled differently (btn--special); calls the same
     medication endpoint as GET /MedicationRequest below -->
<button class="btn btn--special"
        hx-get="/fhir/medication"
        hx-target="#result"
        hx-swap="innerHTML"
        hx-indicator="#fhir-loading"
        hx-disabled-elt="this">
  Patient Summary
</button>

<button class="btn"
        hx-get="/fhir/patient"
        hx-target="#result"
        hx-swap="innerHTML"
        hx-indicator="#fhir-loading"
        hx-disabled-elt="this">
  GET /Patient
</button>

<button class="btn"
        hx-get="/fhir/medication"
        hx-target="#result"
        hx-swap="innerHTML"
        hx-indicator="#fhir-loading"
        hx-disabled-elt="this">
  GET /MedicationRequest
</button>

<button class="btn"
        hx-get="/fhir/labreport"
        hx-target="#result"
        hx-swap="innerHTML"
        hx-indicator="#fhir-loading"
        hx-disabled-elt="this">
  GET /LabReports
</button>

<button class="btn"
        hx-get="/fhir/vitalsigns"
        hx-target="#result"
        hx-swap="innerHTML"
        hx-indicator="#fhir-loading"
        hx-disabled-elt="this">
  GET /VitalSigns
</button>
```

| Attribute | Effect |
|---|---|
| `hx-get="..."` | On click, HTMX sends a GET request to the specified FastAPI endpoint |
| `hx-target="#result"` | The server's HTML response is injected into the element with `id="result"` |
| `hx-swap="innerHTML"` | The inner content of `#result` is replaced (the `<div>` itself stays) |
| `hx-indicator="#fhir-loading"` | The loading span fades in while the request is in flight |
| `hx-disabled-elt="this"` | The button is disabled for the duration of the request to prevent double-clicks |

All buttons share the same `#result` target — clicking any button replaces whatever was previously displayed. No page navigation occurs. The session cookie is sent automatically with each HTMX request because HTMX issues a same-origin HTTP GET like any other browser request.

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

The token exchange in `auth.py` and all FHIR calls in `pages.py` wrap their `httpx` calls in `try/except httpx.TransportError`:

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

All error paths in all FHIR route handlers return through this helper. It produces a styled HTML fragment rather than a JSON error body or a full error page, so HTMX can inject it directly into `#result`. The optional `detail` argument adds a second block containing raw response text — shown when Epic returns a non-2xx status code with a body describing the problem.

---

## GET /MedicationRequest

### Why MedicationRequest requires a patient ID

`GET /Patient` uses a special `me` context — Epic automatically scopes it to the patient associated with the OAuth session. `MedicationRequest` has no such shortcut. It is always a search against a specific patient and requires an explicit query parameter:

```
GET /MedicationRequest?patient=<fhir_patient_id>
```

Without the `patient` parameter, Epic rejects the request. The patient FHIR ID must be known before the call is made.

### Where the patient ID comes from

Epic includes a `patient` field in the token response for patient-scoped standalone launches. App2 captures this value during `/auth/callback` and stores it in the server-side token store alongside the access token:

```python
request.app.state.token_store[session_id] = {
    "access_token": token_data["access_token"],
    ...
    "patient": token_data.get("patient", ""),
}
```

`token_data.get("patient", "")` returns an empty string when Epic does not include a patient context — this happens when the launch is not patient-scoped (e.g., a provider browsing without selecting a specific patient). The `fhir_get_medication_request` handler checks for this and returns an informative error fragment rather than making a doomed API call.

### Scope and Epic app registration

Two things must be in place for the MedicationRequest call to succeed:

1. **Scope**: `patient/MedicationRequest.read` must be included in `EPIC_SCOPE` in `.env` (Epic abbreviates this as `patient/MedicationRequest.r` in the token response).
2. **App registration capability**: The **MedicationRequest.Read (R4)** capability must be enabled in the Epic developer portal app registration. If the capability is not registered, Epic returns a 403 or 400 error even when the scope is correct.

To enable the capability:
1. Log into [open.epic.com](https://open.epic.com) and open the app registration
2. Under **API Capabilities**, find and enable **MedicationRequest.Read (R4)**
3. Ensure `patient/MedicationRequest.read` is in `EPIC_SCOPE` in `.env`

### The route: `GET /fhir/medication`

The route handler follows the same six-step pattern as `fhir_get_patient`, with one additional check for the patient ID inserted between the token lookup and the expiry check:

**Step 1 — Read the session ID**

```python
session_id = request.session.get("session_id")
```

**Step 2 — Look up the access token and patient ID**

```python
token_entry = request.app.state.token_store.get(session_id, {})
access_token = token_entry.get("access_token")
patient_id = token_entry.get("patient", "")
```

Both values were written to the token store during `/auth/callback`. If `patient_id` is empty, the handler returns an error fragment explaining that a patient-scoped launch is required, rather than making a request Epic will reject:

```python
if not patient_id:
    return _error_html(
        "No patient ID in session. "
        "MedicationRequest requires a patient-scoped launch. "
        "Ensure the <code>launch/patient</code> scope is included and "
        '<a href="/auth/login">reconnect to Epic Sandbox</a>.'
    )
```

**Step 3 — Check token expiry**

Same as `fhir_get_patient`: read `token_expires_at` from the session cookie and compare to `datetime.now(timezone.utc)`.

**Step 4 — Call Epic FHIR with the Bearer token and patient parameter**

```python
response = await request.app.state.http_client.get(
    f"{settings.epic_fhir_base_url}/MedicationRequest",
    params={"patient": patient_id},
    headers={
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/fhir+json",
    },
)
```

`httpx` serializes the `params` dict as a URL query string (`?patient=<id>`). Epic's FHIR server requires this parameter to identify which patient's medication orders to return.

**Step 5 — Handle non-2xx responses**

Same as `fhir_get_patient`: non-2xx status returns an error fragment with the raw response body in the `detail` block.

**Step 6 — Format and return the FHIR Bundle**

```python
formatted_json = json.dumps(response.json(), indent=2)
return HTMLResponse(content=f'<pre class="fhir-json">{formatted_json}</pre>')
```

Epic responds with a FHIR Bundle where each `entry` is a `MedicationRequest` resource representing a single prescription or medication order for the patient. The Bundle is pretty-printed and injected into `#result` by HTMX.

---

## GET /Observation: Lab Reports and Vital Signs

### The Observation resource

`Observation` is FHIR's catch-all resource for clinical measurements and findings. A single resource type covers an enormous range of data: lab results, vital signs, SDOH questionnaire responses, smoking status, body measurements, and more. The resource has a consistent structure regardless of what kind of measurement it contains:

```json
{
  "resourceType": "Observation",
  "id": "...",
  "status": "final",
  "category": [{ "coding": [{ "system": "...", "code": "vital-signs" }] }],
  "code": { "coding": [{ "system": "http://loinc.org", "code": "8867-4", "display": "Heart rate" }] },
  "subject": { "reference": "Patient/abc123" },
  "effectiveDateTime": "2024-03-15T10:30:00Z",
  "valueQuantity": { "value": 72, "unit": "beats/minute" }
}
```

The `code` element identifies what was measured (usually a LOINC code). The `value[x]` element holds the result — a quantity with unit, a coded value, a string, or a boolean depending on the measurement type. The `category` element identifies the clinical domain.

### The category system

Because Observation covers so many domains, filtering by `category` is essential for retrieving a coherent subset. The standard category system is `http://terminology.hl7.org/CodeSystem/observation-category`, and the codes relevant to app2 are:

| Code | Clinical domain | Examples |
|---|---|---|
| `laboratory` | Lab results | CBC, metabolic panel, lipid panel, urinalysis, cultures |
| `vital-signs` | Vital sign measurements | Blood pressure, heart rate, temperature, SpO2, height, weight, BMI |
| `survey` | Questionnaire responses | SDOH assessments, PHQ-9, GAD-7 |

A single patient visit may produce Observations across multiple categories. Filtering by category is how you pull a coherent set — lab results separately from vitals — rather than retrieving everything at once.

### Why both endpoints use `GET /Observation`

Lab reports and vital signs share a single FHIR resource type. The only difference between the two FHIR calls is the `category` query parameter value. Both routes in app2 call the same Epic FHIR endpoint; the category parameter routes the query to the appropriate data:

```
GET /Observation?patient=<id>&category=laboratory    → lab results Bundle
GET /Observation?patient=<id>&category=vital-signs   → vital signs Bundle
```

### Scope requirements and Epic's category-specific grants

Epic implements Observation access per category in both the app registration and the token response. Each category that has been enabled in the developer portal appears as a separate scope entry using SMART v2's parameterized scope format:

```
patient/Observation.r?category=http://terminology.hl7.org/CodeSystem/observation-category|laboratory
patient/Observation.r?category=http://terminology.hl7.org/CodeSystem/observation-category|vital-signs
```

Epic enforces these grants independently at the API level. A token that includes the `laboratory` grant but not `vital-signs` will succeed on lab requests and return 403 on vital signs requests — even though both calls target the same resource type. This is different from resources like MedicationRequest, where a single `patient/MedicationRequest.r` scope covers the entire resource.

**Diagnosing a 403**: check the Scope row on the home page after reconnecting. If you see `patient/Observation.r?category=...|survey` but not `laboratory` or `vital-signs`, the relevant capabilities are not yet registered or provisioned in the Epic developer portal. See the **API Capabilities and Category-Specific Registration** subsection in the Epic Sandbox App Registration section.

### Result volume and pagination

Observation bundles can be significantly larger than MedicationRequest bundles. A patient with years of clinical history may have hundreds of lab results or vital sign measurements. Epic returns results in a single bundle by default, up to its internal page size limit.

**To limit results**, add `_count` as a third query parameter:

```python
params={"patient": patient_id, "category": "laboratory", "_count": 20}
```

When more results exist beyond `_count`, Epic includes a `link` array in the Bundle with a `next` relation containing the URL for the next page:

```json
{
  "resourceType": "Bundle",
  "link": [
    { "relation": "self", "url": "..." },
    { "relation": "next", "url": "https://fhir.epic.com/.../Observation?patient=...&category=laboratory&sessionID=...&page=2" }
  ],
  "total": 147,
  "entry": [ ... ]
}
```

App2 does not currently implement `_count` or pagination — the full result set is returned in a single request. This is sufficient for development against the sandbox test patient, whose Observation history is limited. Before deploying against real patients, add `_count` to the params dict and implement pagination if needed.

**Empty bundles are valid**: if the sandbox test patient has no recorded lab results or vital signs, Epic returns a valid 200 response with `"total": 0` and an empty `entry` array. The route handler formats and returns this normally — the `<pre>` block will show the empty Bundle structure. This is correct behavior, not an error.

### The route handlers: `fhir_get_lab_report` and `fhir_get_vital_signs`

Both handlers in `pages.py` follow the identical six-step pattern as `fhir_get_medication_request`. The only structural difference is the `category` value passed in step 4:

**Step 1** — Read `session_id` from the session cookie.

**Step 2** — Look up `access_token` and `patient` from the token store. The `patient` FHIR ID is needed as a required search parameter, identical to MedicationRequest. If absent, an informative error fragment is returned.

**Step 3** — Check token expiry via `token_expires_at` in the session cookie.

**Step 4** — Call Epic FHIR:

```python
# Lab reports
params={"patient": patient_id, "category": "laboratory"}

# Vital signs
params={"patient": patient_id, "category": "vital-signs"}
```

Both use `settings.epic_fhir_base_url + "/Observation"` as the URL and the same `Authorization: Bearer` and `Accept: application/fhir+json` headers used by all other FHIR route handlers.

**Step 5** — Handle non-2xx responses via `_error_html`.

**Step 6** — `json.dumps(response.json(), indent=2)` and return as `HTMLResponse` wrapped in `<pre class="fhir-json">`.

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
| `GET` | `/fhir/medication` | HTMX endpoint — calls Epic FHIR `GET /MedicationRequest?patient=<id>`; returns HTML fragment |
| `GET` | `/fhir/labreport` | HTMX endpoint — calls Epic FHIR `GET /Observation?patient=<id>&category=laboratory`; returns HTML fragment |
| `GET` | `/fhir/vitalsigns` | HTMX endpoint — calls Epic FHIR `GET /Observation?patient=<id>&category=vital-signs`; returns HTML fragment |
| `GET` | `/health` | System health check — returns app name, version, environment |

---

## `__init__.py`

`app2/__init__.py` must exist (it can be empty) for Python to treat `app2` as a package. Without it, the `uvicorn app2.main:app` invocation from the project root will fail with a `ModuleNotFoundError`.

---

## `services/patient_service.py`

`app2/services/patient_service.py` is a standalone synchronous module used for CLI experimentation and development testing. It is **not** wired into the main application routes. It uses the synchronous `requests` library (rather than the async `httpx` used throughout the rest of app2) to call `GET /Patient` directly against the Epic FHIR sandbox.

Because it uses `requests` synchronously and omits authentication headers, it is not suitable for production use. Its value is as a quick sanity-check tool for verifying the FHIR base URL and basic connectivity outside of the full OAuth flow.

---

## OCI Deployment Notes

The deployment approach mirrors the local setup: lift-and-shift to an OCI VM running the same uvicorn process.

Changes required for production:

- Set `https_only=True` in `SessionMiddleware` (requires HTTPS termination at a reverse proxy such as nginx)
- Set a strong `SESSION_SECRET_KEY` in the production environment (not in `.env` committed to git)
- Replace `app.state.token_store` (in-memory dict) with Redis or another persistent store so sessions survive server restarts and work across multiple workers
- Run uvicorn behind a process manager (e.g., systemd or supervisor) rather than with `--reload`
- Set `APP_REDIRECT_URI` to the production HTTPS callback URL and update it in the Epic app registration
