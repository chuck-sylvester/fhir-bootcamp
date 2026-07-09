# app4 — Epic Sandbox OAuth 2.0 Integration

**Bun + Hono + HTMX + TypeScript**

app4 is a full-stack web application that replicates every feature of app2 using a TypeScript-native technology stack. It uses **Bun** as the runtime, **Hono** as the web framework, and **HTMX** for client-side interactivity — the same hypermedia-first approach as app2, rewritten in TypeScript. The rendering model, session architecture, OAuth flow, and HTMX patterns are structurally identical to app2; only the implementation language and framework differ.

This guide is self-contained. It covers every concept, configuration, and implementation step needed to build app4 from scratch, including TypeScript, HTMX, OAuth, FHIR, and Epic registration. No other guide is required.

---

## What app4 Does

- Presents a landing page with a "Connect to Epic Sandbox" button
- Redirects the user to Epic's login/consent page (OAuth 2.0 Authorization Code flow)
- Receives the authorization code callback from Epic
- Exchanges the code for an access token via a server-to-server POST (back-channel)
- Stores the access token server-side; places only a lightweight encrypted session cookie in the browser
- Displays session status (active/expired), token expiration time, and granted scopes on the home page
- Decodes the OIDC ID token server-side and presents its identity claims in a browser modal
- Supports logout (clears session cookie and removes server-side token)
- Provides a patient portal with HTMX-wired buttons calling Epic FHIR R4 endpoints: `GET /Patient`, `GET /MedicationRequest`, `GET /Observation` (lab reports), `GET /Observation` (vital signs)

---

## App2 vs App4: Technology Stack Comparison

| Concern | app2 (Python) | app4 (Bun + Hono) |
|---|---|---|
| **Runtime** | CPython 3.12 | Bun 1.x |
| **Web framework** | FastAPI (ASGI) | Hono |
| **HTML rendering** | Jinja2 templates | Hono JSX (server-side only) |
| **Client interactivity** | HTMX | HTMX (identical) |
| **HTTP client (outbound)** | `httpx.AsyncClient` | `fetch` (built-in to Bun) |
| **Session cookies** | Starlette `SessionMiddleware` (HMAC-signed) | `hono-sessions` (AES-GCM encrypted) |
| **Config / env vars** | `pydantic-settings` + `.env` | Bun native `.env` loading |
| **Language** | Python 3.12 | TypeScript (no compile step) |
| **Package manager** | pip + requirements.txt | Bun (built-in) |
| **Routing** | `APIRouter` + `include_router` | `new Hono()` + `app.route()` |
| **Startup** | `uvicorn app2.main:app --reload --port 8000` | `bun run --hot src/index.ts` |
| **Build step** | None | None |

The HTMX interaction model, OAuth flow, server-side token store, and FHIR API call patterns are structurally identical to app2. The hypermedia-first architecture is carried forward into TypeScript.

---

## The Hypermedia-First Philosophy

app2's architecture rests on a principle: the server produces HTML, and the browser displays it. HTMX extends this by allowing the server to return HTML *fragments* that update part of an existing page without a full navigation. The browser never manages application state; the server always produces the authoritative view.

This is the inverse of the Single Page Application model, where the server returns JSON and the browser builds the HTML. HTMX keeps rendering on the server — where the access token, session, and business logic already live — and sends only what the browser needs to see. The result is less JavaScript in the browser, a simpler mental model, and stronger security (sensitive credentials never leave the server).

app4 carries this philosophy into TypeScript. The stack changes; the architecture does not.

---

## Technology Primer

### JavaScript and TypeScript

**JavaScript** is the native language of browsers and, via Node.js and Bun, is used for server-side programs. It is dynamically typed — variables have no declared type; any variable can hold any value at any time.

**TypeScript** is a superset of JavaScript created by Microsoft. It adds optional static type annotations that are checked at development time:

```typescript
// JavaScript — no types; passing the wrong type is a silent runtime bug
function greet(name) {
  return "Hello, " + name;
}

// TypeScript — type error caught before the code runs
function greet(name: string): string {
  return "Hello, " + name;
}
```

TypeScript is compiled ("transpiled") to plain JavaScript before execution. Bun runs TypeScript natively — it strips the type annotations at runtime and executes the resulting JavaScript directly, with no separate compilation step. The TypeScript compiler (`tsc`) is still useful for catching type errors without running the code:

```bash
bunx tsc --noEmit  # type-check only; no output files
```

**Key TypeScript concepts used in app4:**

| Concept | Syntax | Example |
|---|---|---|
| Type annotation | `name: Type` | `const id: string = "abc"` |
| Optional property | `?` suffix | `refreshToken?: string` |
| Union type | `\|` | `string \| undefined` |
| Interface | `interface` | `interface TokenEntry { ... }` |
| Generic type | `<T>` | `Map<string, TokenEntry>` |
| Non-null assertion | `!` | `process.env.SECRET!` |
| Type cast | `as` | `session.get('id') as string` |

**TypeScript vs Python type hints**: Python type hints (`def foo(x: str) -> int`) are decoration — the Python interpreter ignores them at runtime. TypeScript types are erased at compile time but *checked* before erasure — the compiler rejects code with type errors before it ever runs. This is the source of TypeScript's value: errors surface in the editor, not in production.

### Async/Await and Promises

JavaScript is single-threaded but handles I/O concurrently via an event loop — the same model as Python's `asyncio`. A function that does I/O (network call, file read) suspends itself rather than blocking, allowing other work to proceed.

**Promises** are JavaScript's primitive for deferred values. A `Promise<string>` is a value that will eventually resolve to a `string` (or reject with an error).

**`async`/`await`** is syntactic sugar over Promises, directly mirroring Python's `async def`/`await`:

```python
# Python
async def get_patient(token: str) -> dict:
    response = await http_client.get(url, headers={"Authorization": f"Bearer {token}"})
    return response.json()
```

```typescript
// TypeScript (equivalent)
async function getPatient(token: string): Promise<object> {
  const response = await fetch(url, { headers: { Authorization: `Bearer ${token}` } })
  return response.json()
}
```

**Rules** (same as Python):
- A function that uses `await` must be declared `async`
- An `async` function always returns a `Promise`, even when you `return` a plain value
- `await` can only appear inside an `async` function

**Error handling**: use `try/catch`. JavaScript does not have typed exception hierarchies like Python — catch `unknown` and narrow with `instanceof`:

```typescript
try {
  const response = await fetch(url)
} catch (err) {
  if (err instanceof TypeError) {
    // Network-level failure — fetch throws TypeError when no response arrives
    console.error('Network error:', err.message)
  }
}
```

### ES Modules

TypeScript (and modern JavaScript) organize code into modules using `import` and `export`:

```typescript
// Export from one file
export function buildAuthUrl(clientId: string): string { ... }
export interface TokenEntry { accessToken: string }
export const tokenStore = new Map<string, TokenEntry>()

// Import in another file
import { buildAuthUrl, tokenStore } from './lib/tokenStore'
import type { TokenEntry } from './lib/tokenStore'  // type-only import (erased at compile time)
```

`import type` imports only the TypeScript type, not the runtime value. It guarantees the import is erased at compile time and adds no runtime dependency. Use it when you only need a type for annotation purposes.

**Path resolution**: imports starting with `./` or `../` are relative to the current file. Imports without a path prefix are package names resolved from `node_modules`. In app4, all internal imports use relative paths.

### Bun: A New JavaScript Runtime

Bun is a JavaScript and TypeScript runtime built from scratch (in Zig), designed to be fast and to eliminate friction accumulated in the Node.js ecosystem. From a developer experience perspective, the three most important things it eliminates:

**No TypeScript compilation step.** Node.js cannot run `.ts` files — you must compile first. Bun runs `.ts` files natively. You write TypeScript; you run it immediately.

```bash
# Node.js — requires compilation
npx ts-node src/index.ts       # slow startup via ts-node
npx tsc && node dist/index.js  # two-step compile then run

# Bun — runs TypeScript directly
bun run src/index.ts           # instant
```

**Built-in package management.** `bun install` is 10–25x faster than `npm install`, using a binary lockfile and global cache. The commands mirror npm:

```bash
bun install          # install from package.json  (= npm install)
bun add hono         # add a dependency           (= npm install hono)
bun add -d @types/bun # add dev dependency        (= npm install --save-dev)
bun run dev          # run a script               (= npm run dev)
```

**Built-in `fetch`, crypto, and Web APIs.** The same `fetch()`, `crypto.subtle`, and `URL` that run in browsers also run in Bun — no polyfill or import needed. `fetch()` is the outbound HTTP client for all FHIR API calls in app4, replacing Python's `httpx`.

**`bun run --hot`** — hot module replacement during development. Changed files are reloaded in place without restarting the process. Unlike Python's `uvicorn --reload` (which kills the process and clears all in-memory state), Bun's `--hot` preserves module-level state — including the `tokenStore` Map — across file changes. You can edit a route handler mid-session without losing your OAuth token.

### Hono: A FastAPI-like Web Framework

Hono (炎 — "flame" in Japanese) is a small, fast web framework for TypeScript. Its API is structurally similar to FastAPI:

```python
# FastAPI (Python) — app2's router pattern
from fastapi import APIRouter
router = APIRouter()

@router.get("/login")
async def auth_login(request: Request):
    return RedirectResponse(url=authorization_url)
```

```typescript
// Hono (TypeScript) — app4's equivalent
import { Hono } from 'hono'
const auth = new Hono()

auth.get('/login', async (c) => {
  return c.redirect(authorizationUrl)
})
```

#### The Hono Context Object: `c`

Every Hono route handler receives a single argument — the **context** (`c` by convention). It is the primary integration point for everything that crosses the HTTP boundary, equivalent to FastAPI's `Request` object:

```typescript
// Reading query parameters  (= request.query_params.get("code") in FastAPI)
const code = c.req.query('code')

// Reading a path parameter  (= request.path_params["id"])
const id = c.req.param('id')

// Reading a request header
const auth = c.req.header('Authorization')

// Returning an HTML response  (= HTMLResponse(...) in FastAPI)
return c.html('<p>Hello</p>')

// Returning JSON  (= JSONResponse(...))
return c.json({ status: 'ok' })

// Returning a redirect  (= RedirectResponse(url=...))
return c.redirect('/home', 302)

// Returning plain text with a status code
return c.text('Not found', 404)

// Storing a value in the context for downstream handlers
c.set('userId', '123')

// Retrieving a value set by earlier middleware
const userId = c.get('userId')
```

`c.set()` and `c.get()` are how middleware passes data to route handlers. The session middleware stores the session object with `c.set('session', session)`, which route handlers retrieve with `c.get('session')`. This is the Hono equivalent of Starlette's `request.session`.

#### Routing and Subrouters

Hono's `app.route()` mirrors FastAPI's `include_router`:

```python
# FastAPI (app2)
app.include_router(auth_router, prefix="/auth")
```

```typescript
// Hono (app4)
app.route('/auth', auth)  // all routes defined on `auth` get the /auth prefix
```

A route defined as `auth.get('/login', ...)` becomes `GET /auth/login` in the full application.

#### Middleware

Hono middleware is applied with `app.use()`. Code before `await next()` runs on the way in; code after runs on the way out:

```typescript
app.use('*', async (c, next) => {
  console.log(`${c.req.method} ${c.req.url}`)
  await next()  // call the next handler in the chain
  console.log(`Response: ${c.res.status}`)
})
```

This is the same pattern as Starlette's middleware `call_next(request)` in app2.

### Hono JSX: Server-Side HTML Rendering

Hono has a built-in JSX renderer. It is **not React** — it is Hono's own JSX implementation that runs entirely on the server and produces HTML strings. There is no browser JavaScript, no virtual DOM, no hydration, and no client-side state.

The JSX syntax is identical to React JSX, but the behavior is like Jinja2: it renders to a string on the server and sends finished HTML to the browser.

**Jinja2 vs Hono JSX — the key equivalences:**

| Jinja2 (app2) | Hono JSX (app4) |
|---|---|
| `{{ variable }}` | `{variable}` |
| `{% if x %}...{% endif %}` | `{x ? <A /> : <B />}` (ternary) |
| `{% if x %}...{% endif %}` (no else) | `{x && <A />}` (short-circuit) |
| `{% for item in items %}` | `{items.map(item => <li>{item}</li>)}` |
| `{% extends "portal.html" %}` | Import and compose JSX components |
| `{% block content %}` | `{children}` prop in a Layout component |
| `{{ html_string \| safe }}` | `dangerouslySetInnerHTML={{ __html: html }}` |
| `{# comment #}` | `{/* comment */}` |
| `class="btn"` | `className="btn"` |

**`class` becomes `className`**: `class` is a reserved word in JavaScript (it defines a class/object). JSX uses `className` instead — TypeScript will give you a type error if you write `class=`.

**Template inheritance** works through component composition rather than block inheritance:

```tsx
// views/Layout.tsx — equivalent of portal.html in app2
import type { FC, Child } from 'hono/jsx'

interface LayoutProps {
  title: string
  children: Child   // Child = JSX content passed between the opening and closing tag
}

const Layout: FC<LayoutProps> = ({ title, children }) => (
  <html>
    <head>
      <title>{title}</title>
      <link rel="stylesheet" href="/static/css/main.css" />
      <script src="https://unpkg.com/htmx.org@2.0.4"></script>
    </head>
    <body>{children}</body>
  </html>
)

// views/Patient.tsx — equivalent of patient.html extending portal.html
import Layout from './Layout'

const Patient: FC = () => (
  <Layout title="Patient Portal">
    {/* children go here — equivalent of {% block content %} */}
    <button hx-get="/fhir/patient" hx-target="#result">GET /Patient</button>
    <div id="result"></div>
  </Layout>
)
```

**`onclick` uses HTML attribute syntax, not React's camelCase**: Hono JSX outputs HTML strings. The `onclick` attribute lands in the browser as raw HTML — the browser evaluates the string as JavaScript. React's `onClick` is a synthetic event system that requires React's JavaScript runtime in the browser. Since app4 has no client-side React, use lowercase HTML event attributes:

```tsx
// ✓ Correct for Hono JSX
<button onclick="document.getElementById('dialog').showModal()">Open</button>

// ✗ Wrong — onClick only works with React's synthetic events
<button onClick={() => ...}>Open</button>
```

### hono-sessions: Session Management

`hono-sessions` is a session middleware package for Hono. App4 uses its `CookieStore`, which encrypts session data with AES-GCM and stores it in the browser cookie — similar in function to Python's `itsdangerous` in app2, but with encryption rather than only signing (the payload is ciphertext, not readable base64 JSON).

```typescript
import { sessionMiddleware, CookieStore } from 'hono-sessions'

// Apply globally in src/index.ts
app.use('*', sessionMiddleware({
  store: new CookieStore(),
  encryptionKey: process.env.SESSION_SECRET_KEY,
  expireAfterSeconds: 3600,
  cookieOptions: {
    name: 'app4_session',
    sameSite: 'Lax',
    httpOnly: true,
    secure: false,  // true in production (requires HTTPS)
  },
}))

// In any route handler:
const session = c.get('session')
const sessionId = await session.get('sessionId')  // read a value
await session.set('sessionId', newId)             // write a value
await session.deleteSession()                     // destroy the session (logout)
```

Session values are accessed via async `get()`/`set()` methods. The `await` is required because the CookieStore performs crypto operations. This differs from Starlette's `request.session`, which is a plain synchronous dict.

### HTMX

HTMX is a JavaScript library (loaded from a CDN `<script>` tag, ~14 KB) that extends HTML with new attributes, enabling HTTP requests and DOM updates without writing JavaScript. The philosophical foundation: the server produces HTML; HTMX delivers it to the right place on the page.

#### The Hypermedia Model

HTMX endpoints must return HTML, not JSON:

```typescript
// Wrong for HTMX — the browser receives JSON and renders it as raw text
return c.json({ status: 'ok', data: patientBundle })

// Right for HTMX — the browser injects the HTML directly into #result
return c.html(`<pre class="fhir-json">${formatted}</pre>`)
```

In an HTMX application, the server is not a data provider — it is an HTML renderer. The server decides what the user sees by choosing what HTML to return.

#### HTMX Attribute Vocabulary

Five attributes are used throughout app4's portal page:

| Attribute | Purpose |
|---|---|
| `hx-get="/path"` | On trigger, send a GET request to this URL |
| `hx-target="#result"` | CSS selector for the element to update with the response |
| `hx-swap="innerHTML"` | How to insert the response (replace inner content of target) |
| `hx-indicator="#fhir-loading"` | Show this element while the request is in flight |
| `hx-disabled-elt="this"` | Disable this element for the duration of the request |

Additional attributes available but not used in app4:

| Attribute | Use case |
|---|---|
| `hx-post` / `hx-put` / `hx-delete` | Other HTTP methods |
| `hx-trigger` | Control when the request fires: `click` (default for buttons), `change`, `keyup delay:500ms`, `every 2s` (polling), `intersect` (scroll into view) |
| `hx-push-url` | Update the browser address bar without navigation |
| `hx-boost` | Upgrade all `<a>` and `<form>` elements in a subtree to HTMX requests |
| `hx-confirm` | Show a browser confirm dialog before issuing the request |

#### Swap Strategies

`hx-swap` controls how the response HTML is placed relative to the target:

| Value | Effect |
|---|---|
| `innerHTML` | Replace the target's inner content (the target element itself stays) |
| `outerHTML` | Replace the entire target element |
| `beforeend` | Append as the last child — ideal for infinite scroll or append-only lists |
| `afterbegin` | Insert as the first child |
| `beforebegin` / `afterend` | Insert before/after the target in the DOM |
| `delete` | Remove the target from the DOM (response body ignored) |
| `none` | Do not modify the DOM — for side-effect-only requests |

App4 uses `innerHTML` for all FHIR endpoints. The `<div id="result">` container stays; only its inner content is replaced on each button click.

#### Loading Indicators

HTMX adds the CSS class `htmx-request` to the element initiating a request while the request is in flight. `hx-indicator` designates a separate element that HTMX reveals during this time by transitioning its opacity:

```html
<!-- Button: HTMX adds htmx-request class while request is in flight -->
<button hx-get="/fhir/patient" hx-indicator="#fhir-loading">GET /Patient</button>

<!-- Indicator: hidden by default via .htmx-indicator CSS; revealed when active -->
<span id="fhir-loading" class="htmx-indicator">Loading&hellip;</span>
```

The `.htmx-indicator` class sets `opacity: 0` and `transition: opacity 200ms` by default (from the HTMX CDN script). No JavaScript animation code is needed.

#### Non-2xx Responses and the Error HTML Pattern

HTMX does **not** swap the response body into the target when the server returns a 4xx or 5xx status code. It fires an `htmx:responseError` event and leaves the page unchanged. This means HTMX endpoints that encounter errors must return **HTTP 200** with styled error HTML:

```typescript
// Wrong: HTMX ignores this response body; #result stays unchanged
return c.html('<p>Something failed.</p>', 400)

// Right: HTMX swaps the error HTML into #result
return c.html(errorHtml('Something failed.'))  // returns HTTP 200 with error markup
```

This is why the `errorHtml()` helper exists in `src/routes/fhir.ts` and why every error path returns through it. The user sees the error in context; no full-page reload is needed.

#### `hx-disabled-elt` — Preventing Double Submission

Without `hx-disabled-elt="this"`, a user can click a button multiple times before the first request completes, queuing duplicate server calls. Always include this attribute on HTMX action buttons:

```html
<button
  hx-get="/fhir/patient"
  hx-target="#result"
  hx-swap="innerHTML"
  hx-indicator="#fhir-loading"
  hx-disabled-elt="this"
>GET /Patient</button>
```

---

## Architecture Deep Dive

### The Request Lifecycle

A complete HTMX interaction through app4 follows this path — using "GET /Patient" button as the example:

```
Browser (HTMX)
  │
  │  1. HTMX intercepts the button click.
  │     Issues: GET /fhir/patient
  │     With:   session cookie (same-origin, sent automatically)
  │
  ▼
Hono (Bun HTTP server)
  │
  │  2. Session middleware decodes the encrypted cookie on the way in.
  │     Stores the session object in context via c.set('session', session).
  │
  │  3. Router matches GET /fhir/patient → fhirGetPatient handler.
  │
  │  4. Handler reads sessionId via c.get('session').get('sessionId').
  │     Looks up accessToken from the module-level tokenStore Map.
  │
  │  5. Handler calls Epic FHIR using fetch().
  │     Bun's event loop suspends (await) during Epic's response time.
  │
  ▼
fetch() → Epic FHIR Server
  │
  │  6. GET /FHIR/R4/Patient
  │     Authorization: Bearer <accessToken>
  │     Accept: application/fhir+json
  │
  │  7. Epic validates the JWT, checks scope, returns a FHIR Bundle.
  │
  │  8. fetch() resolves with the response.
  │
  ▼
Hono handler
  │
  │  9. JSON.stringify(bundle, null, 2) — pretty-print.
  │     Returns: c.html('<pre class="fhir-json">...</pre>')
  │
  ▼
Browser (HTMX)
  │
  │  10. HTMX receives the HTML fragment.
  │      Injects it into #result using innerHTML swap.
  │      No navigation. No page reload.
  │
  ▼
  Page updates in place.
```

### Token Store

```typescript
// src/lib/tokenStore.ts

export interface TokenEntry {
  accessToken: string
  refreshToken: string
  scope: string
  idToken: string     // OIDC identity JWT — decoded server-side for the ID Token dialog
  patientId: string   // FHIR patient ID from Epic's token response; required for MedicationRequest
}

// Module-level Map — created once, persists for the server's lifetime.
// Bun --hot reloads changed modules but preserves module-level state,
// so this Map survives file changes during development (unlike uvicorn --reload).
export const tokenStore = new Map<string, TokenEntry>()
```

### Why a Server-Side Token Store?

Epic access tokens are JWTs, typically ~880 characters. When combined with a refresh token, ID token, and scope string, and then encrypted and base64-encoded into a session cookie, the total easily exceeds the **4096-byte browser cookie size limit**. Browsers silently discard oversized cookies rather than returning an error, which causes the session to vanish without any obvious indication of why.

The solution: keep tokens on the server and store only a short random `sessionId` in the cookie. The cookie carries lightweight metadata (session ID, expiry timestamp, scope string); the `tokenStore` Map holds the actual tokens:

```
Browser cookie (encrypted, ~200 bytes):
  { sessionId: "a3f9...", tokenExpiresAt: "2026-06-17T...", scope: "openid fhirUser" }

Server tokenStore Map (in memory, never sent to browser):
  "a3f9..." → { accessToken: "eyJ...", idToken: "eyJ...", patientId: "abc123", ... }
```

**Limitation**: the `tokenStore` is in-memory and process-local. It is cleared when the Bun process restarts. In production, replace it with Redis or another persistent store.

### Scope and Cookie Size

Even with tokens removed from the cookie, the `scope` string can cause overflow. When "All FHIR R4 scopes" are selected during Epic app registration, Epic returns a scope string of approximately 5,000 characters. A minimal scope set is strongly recommended:

```
openid fhirUser launch/patient patient/Patient.read patient/Observation.read patient/Condition.read patient/MedicationRequest.read
```

---

## Directory Structure

```
app4/
├── src/
│   ├── index.ts              ← Hono app: middleware, routes, server (like main.py)
│   ├── config.ts             ← Typed env var access (like config.py)
│   ├── lib/
│   │   ├── tokenStore.ts     ← In-memory token store (like app.state.token_store)
│   │   └── jwt.ts            ← JWT decode utility
│   ├── routes/
│   │   ├── auth.ts           ← /auth/* routes (like routers/auth.py)
│   │   ├── pages.ts          ← Page routes: /, /patient
│   │   └── fhir.ts           ← /fhir/* HTMX endpoints
│   └── views/                ← Hono JSX templates (like templates/)
│       ├── Layout.tsx         ← Base HTML shell (like portal.html)
│       ├── Home.tsx           ← Home page (like home.html)
│       └── Patient.tsx        ← Patient portal (like patient.html)
├── public/                   ← Static files served at /static
│   ├── css/
│   │   └── main.css
│   └── images/
│       ├── epic-sandbox-logo.png
│       └── favicon.ico
├── .env.local                ← Secrets (gitignored)
├── package.json
└── tsconfig.json
```

---

## Dependencies

| Package | Purpose | app2 equivalent |
|---|---|---|
| `hono` | Web framework | FastAPI |
| `hono-sessions` | Encrypted session cookies | `starlette` SessionMiddleware + `itsdangerous` |

**What is NOT needed** (all built into Bun):
- No HTTP client package — `fetch()` is global
- No template engine — Hono JSX is built into Hono
- No TypeScript compiler package — Bun runs `.ts` natively
- No ASGI/HTTP server — Bun serves HTTP natively
- No `.env` loader — Bun reads `.env` files automatically

---

## Environment Variables

Bun reads `.env` files automatically from the working directory when you run `bun run`. Create `app4/.env.local` — this file is loaded automatically with higher priority than `.env`:

```dotenv
# Application
APP_NAME="FHIR Bootcamp - app4"
APP_ENV=development

# Session encryption key — must be at least 32 characters
# Generate: bun -e "console.log(require('crypto').randomBytes(32).toString('hex'))"
SESSION_SECRET_KEY=<random-string-at-least-32-chars>

# Epic Sandbox OAuth 2.0
EPIC_NONPROD_CLIENT_ID=<your-epic-app-client-id>
EPIC_CLIENT_SECRET=<your-epic-app-client-secret>
EPIC_AUTHORIZE_URL=https://fhir.epic.com/interconnect-fhir-oauth/oauth2/authorize
EPIC_TOKEN_URL=https://fhir.epic.com/interconnect-fhir-oauth/oauth2/token
EPIC_FHIR_BASE_URL=https://fhir.epic.com/interconnect-fhir-oauth/api/FHIR/R4
EPIC_SCOPE="openid fhirUser"

# app4 callback URL — port 8004, same path structure as app2
APP_REDIRECT_URI=http://localhost:8004/auth/callback
```

**Notes:**

- **`SESSION_SECRET_KEY`**: hono-sessions derives an AES-256 encryption key from this password. Must be at least 32 characters. Generate securely: `bun -e "console.log(require('crypto').randomBytes(32).toString('hex'))"`
- **`APP_REDIRECT_URI`**: app4 runs on port 8004 and uses `/auth/callback` (not `/api/auth/callback`). Must be registered in the Epic developer portal.
- **`EPIC_CLIENT_SECRET`**: use the raw secret value shown immediately after app creation in the Epic portal. The portal later displays a masked version — only the value shown at creation time works.
- **`EPIC_SCOPE`**: in Epic's sandbox, this is effectively a trigger for the OAuth flow. Epic grants all registered API capabilities regardless of which specific scopes appear here. `"openid fhirUser"` is sufficient for sandbox development. See **Epic Scope Behavior: Sandbox vs. Production** below.
- **No client-side variable exposure**: Bun has no concept of client-bundled vs server-only env vars. All variables in `.env.local` are server-side — they are never sent to the browser. In Hono's SSR model, the browser receives only HTML; no JavaScript bundle containing server variables is ever shipped.

---

## Epic Sandbox App Registration

app4 uses a **confidential client** registration. A confidential client is appropriate for server-side applications (like this Hono SSR app) that can securely hold a client secret — as opposed to public clients (SPAs, mobile apps) where the secret would be exposed in browser JavaScript.

### Registration Steps

1. Log in to the Epic developer portal at [open.epic.com](https://open.epic.com)
2. Navigate to **My Apps** → **Create** (or open an existing registration and add a redirect URI)
3. Fill in the app details:
   - **Application Audience**: Patients
   - **Is Confidential Client**: Yes
   - **Redirect URI**: `http://localhost:8004/auth/callback`
   - **Scopes**: Select the specific capabilities the app needs — do not select "All FHIR R4 scopes" (see the **Scope and Cookie Size** note in Session Management)
4. Submit and wait for Epic to provision the sandbox app (typically a few minutes)
5. Copy the **Client ID** → set as `EPIC_NONPROD_CLIENT_ID` in `.env.local`
6. Copy the **Client Secret** shown immediately after creation → set as `EPIC_CLIENT_SECRET`

**If you already have an app2 registration**: add `http://localhost:8004/auth/callback` as an additional redirect URI. You can reuse the same client ID and secret — Epic allows multiple redirect URIs per registration.

**JWK Set URLs**: leave blank. These are only needed for `private_key_jwt` authentication. app4 uses `client_secret_post` (credentials sent in the POST body), which requires no JWK configuration.

### API Capabilities and Category-Specific Registration

For most FHIR resource types, enabling one capability grants access to the entire resource. **Observation is different**: Epic registers Observation access per clinical category. Each domain is a separate capability toggle:

| Epic capability name | Category | Token scope format |
|---|---|---|
| Observation.Read — Vital Signs (R4) | `vital-signs` | `patient/Observation.r?category=...observation-category\|vital-signs` |
| Observation.Read — Laboratory (R4) | `laboratory` | `patient/Observation.r?category=...observation-category\|laboratory` |
| Observation.Read — Social History (R4) | `survey` | `patient/Observation.r?category=...observation-category\|survey` |

Epic enforces these grants independently at the API level. A token with only the `laboratory` grant will receive a 403 on a `vital-signs` request even though both use the same resource type.

**After enabling new capabilities in the portal**, allow a few minutes for sandbox provisioning. To confirm: log out of app4, reconnect, and check the Scope row on the home page. The new category scopes should appear in the granted scope string.

### Epic Scope Behavior: Sandbox vs. Production

**In Epic's sandbox**, `EPIC_SCOPE` in `.env.local` is effectively a trigger for the OAuth flow. Epic grants every API capability registered in the developer portal regardless of which specific FHIR scopes appear in the authorization request. `"openid fhirUser"` is sufficient — Epic's sandbox returns a token containing all registered clinical resource scopes regardless of what was requested.

The implication: adding or removing `patient/Observation.read` from `EPIC_SCOPE` has no effect in the sandbox. What controls access is the app registration. If you receive a 403 on a FHIR call, the fix is in the portal (enable the capability), not in `EPIC_SCOPE`.

**In Epic's production environment**, behavior matches the SMART on FHIR specification: the authorization request must explicitly list each scope the app needs, and Epic only grants scopes that were both requested and registered. An app that requests only `"openid fhirUser"` in production receives exactly those two scopes — no clinical resource access. `EPIC_SCOPE` must enumerate all required resource scopes before deploying to production.

---

## OAuth 2.0 Authorization Code Flow

app4 implements the standard SMART on FHIR Authorization Code flow. The steps involving the Epic Auth Server are **front-channel** (the browser follows each redirect). The token exchange is **back-channel** (server-to-server) — the user's browser is never involved and never sees the access token.

### Step 1 — Login redirect (`GET /auth/login`)

The user clicks "Connect to Epic Sandbox." The handler generates a random state value, stores it in the session, builds the Epic authorization URL, and redirects the browser.

```typescript
auth.get('/login', async (c) => {
  // Generate cryptographically random state value (equivalent to secrets.token_urlsafe(32))
  const stateBytes = new Uint8Array(32)
  crypto.getRandomValues(stateBytes)
  const state = btoa(String.fromCharCode(...stateBytes))
    .replace(/\+/g, '-').replace(/\//g, '_').replace(/=/g, '')

  const session = c.get('session')
  await session.set('oauthState', state)

  const params = new URLSearchParams({
    response_type: 'code',
    client_id: config.epicClientId,
    scope: config.epicScope,
    state,
    redirect_uri: config.appRedirectUri,
  })

  return c.redirect(`${config.epicAuthorizeUrl}?${params.toString()}`)
})
```

`URLSearchParams.toString()` percent-encodes special characters including the forward slashes in SMART scope strings (e.g., `patient/Patient.read` → `patient%2FPatient.read`). Epic requires this encoding.

### Step 2 — Epic login and consent

The user's browser follows the redirect to Epic. The user logs in with Epic credentials and reviews the consent screen. After approval, Epic redirects back to `APP_REDIRECT_URI`:

```
GET /auth/callback?code=<authorization_code>&state=<state_value>
```

The authorization code expires in approximately 60 seconds.

### Step 3 — Token exchange (`GET /auth/callback`)

```typescript
auth.get('/callback', async (c) => {
  const code = c.req.query('code')
  const state = c.req.query('state')
  const error = c.req.query('error')

  if (error) {
    return c.text(`Authorization error: ${c.req.query('error_description') ?? error}`, 400)
  }

  // Validate and consume the state — single use
  const session = c.get('session')
  const expectedState = await session.get('oauthState') as string | undefined
  await session.set('oauthState', undefined)  // consume before any other operation

  if (!expectedState || state !== expectedState) {
    return c.text('State mismatch or missing state', 400)
  }

  // Back-channel token exchange
  const body = new URLSearchParams({
    grant_type: 'authorization_code',
    code: code!,
    redirect_uri: config.appRedirectUri,
    client_id: config.epicClientId,
    client_secret: config.epicClientSecret,
  })

  let tokenResponse: Response
  try {
    tokenResponse = await fetch(config.epicTokenUrl, {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: body.toString(),
    })
  } catch (err) {
    return c.text(`Network error during token exchange: ${err}`, 502)
  }

  if (!tokenResponse.ok) {
    const detail = await tokenResponse.text()
    return c.text(`Token exchange failed: ${tokenResponse.status} ${detail}`, 502)
  }

  const tokenData = await tokenResponse.json() as Record<string, string>
  if (tokenData.error) {
    return c.text(`Token error: ${tokenData.error}`, 400)
  }

  // Generate session ID — only this travels to the browser
  const sessionIdBytes = new Uint8Array(16)
  crypto.getRandomValues(sessionIdBytes)
  const sessionId = Array.from(sessionIdBytes)
    .map(b => b.toString(16).padStart(2, '0')).join('')

  // Store full token payload server-side
  tokenStore.set(sessionId, {
    accessToken: tokenData.access_token,
    refreshToken: tokenData.refresh_token ?? '',
    scope: tokenData.scope ?? '',
    idToken: tokenData.id_token ?? '',
    patientId: tokenData.patient ?? '',
  })

  // Write only lightweight metadata to the session cookie
  const expiresAt = new Date(Date.now() + Number(tokenData.expires_in ?? 3600) * 1000)
  await session.set('sessionId', sessionId)
  await session.set('tokenExpiresAt', expiresAt.toISOString())
  await session.set('scope', tokenData.scope ?? '')

  // Return 200 with meta-refresh — see the cross-site cookie note below
  return c.html(
    '<html><head><meta http-equiv="refresh" content="1;url=/"></head></html>'
  )
})
```

**Why meta-refresh instead of a 302 redirect**: some browsers (Chrome, Safari) drop `SameSite=Lax` cookies set on redirect responses at the end of a cross-site redirect chain originating from Epic's domain. Returning HTTP 200 breaks the cross-site context before the browser navigates to `/`, allowing the `Set-Cookie` header to be stored normally. A 302 redirect from the callback to `/` would silently drop the session cookie.

### Step 4 — Redirect home

After the meta-refresh completes, the browser navigates to `/` with the session cookie set. The home page reads the session and renders the authenticated view.

### Step 5 — Logout (`GET /auth/logout`)

```typescript
auth.get('/logout', async (c) => {
  const session = c.get('session')
  const sessionId = await session.get('sessionId') as string | undefined

  if (sessionId) {
    tokenStore.delete(sessionId)  // remove tokens from server-side store
  }

  await session.deleteSession()   // clear the encrypted cookie

  return c.redirect('/')
})
```

---

## OAuth State Parameter and CSRF Protection

### What the state parameter does

The `state` parameter is a cryptographically random value generated at the start of the OAuth flow, sent to the authorization server, and expected back unchanged in the callback. It acts as a nonce binding the callback to the specific browser session that initiated the login.

### The attack it prevents

Without state, the OAuth callback endpoint is vulnerable to a **login CSRF** attack:

1. An attacker initiates an OAuth flow from their browser but does not complete it — capturing the callback URL with a valid `code`
2. The attacker tricks a victim into clicking a crafted link that sends the victim's browser to `/auth/callback` with the attacker's authorization code
3. The victim's browser completes the callback — the server exchanges the code for a token and writes the resulting session cookie to the victim's browser
4. The victim is now logged in as the attacker's identity

In a FHIR context, the stakes are higher than a typical web app: a successful login CSRF could give an attacker access to a patient's health records or allow fraudulent FHIR write operations.

### How the implementation prevents it

With state, step 2 fails because the victim's session contains no `oauthState` (they never initiated a login) — or contains a different value from a legitimate attempt. The check catches two distinct failure modes:

- `expectedState` is `undefined` — no login flow was initiated from this session (replay or forged request)
- `state !== expectedState` — the value Epic returned does not match what was sent (tampered or misrouted callback)

The `pop`/consume-on-read pattern (`set('oauthState', undefined)` immediately after reading) enforces single-use — the same callback cannot be replayed against an active session.

---

## JWT and Token Handling

### What the token endpoint returns

After a successful token exchange, Epic's token endpoint responds with:

```json
{
  "access_token": "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOi4uLn0.SIGNATURE",
  "token_type": "Bearer",
  "expires_in": 3600,
  "scope": "openid fhirUser patient/Patient.r",
  "id_token": "eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOi4uLn0.SIGNATURE"
}
```

The long dot-separated strings starting with `eyJ` are JWTs (JSON Web Tokens). The `access_token` value **is** the JWT — there is no separate token hidden inside it. The JWT string itself is the credential that gets presented to the FHIR server on every API call.

### JWT structure

A JWT is three Base64URL-encoded segments joined by dots:

```
<header>.<payload>.<signature>
```

**Header** — identifies the signing algorithm and key:
```json
{ "alg": "RS256", "typ": "JWT", "kid": "<Epic signing key ID>" }
```

**Payload** — the claims (assertions) about the token:
```json
{
  "iss": "https://fhir.epic.com/interconnect-fhir-oauth/oauth2",
  "sub": "<authenticated user's Epic FHIR ID>",
  "aud": "https://fhir.epic.com/interconnect-fhir-oauth/api/FHIR/R4",
  "client_id": "<your client ID>",
  "iat": 1718000000,
  "exp": 1718003600,
  "scope": "openid fhirUser patient/Patient.r",
  "fhirUser": "https://fhir.epic.com/.../Patient/abc123",
  "patient": "abc123"
}
```

**Signature** — a digital signature computed by Epic using its RSA private key (RS256 = RSA + SHA-256). It can be verified against Epic's public JWKS endpoint, proving the token was issued by Epic and has not been altered.

### Key claims

| Claim | Meaning |
|---|---|
| `iss` | Issuer — Epic's OAuth base URL |
| `sub` | Subject — the authenticated user's Epic internal ID |
| `aud` | Audience — the FHIR base URL the token is intended for |
| `client_id` | The registered client ID of this application |
| `iat` | Issued-at time (Unix timestamp) |
| `exp` | Expiration time (Unix timestamp); Epic typically issues 1-hour tokens |
| `scope` | Granted scopes; Epic abbreviates read as `.r` and search as `.s` |
| `fhirUser` | Full FHIR URL of the authenticated user's Patient or Practitioner resource |
| `patient` | Short-form patient context ID — required for patient-specific FHIR queries |

### `access_token` vs `id_token`

When the `openid` scope is granted, Epic returns two JWTs:

| Field | Purpose | Intended reader |
|---|---|---|
| `access_token` | Authorization credential for FHIR API calls | Epic FHIR server |
| `id_token` | Assertion about who the authenticated user is | The client application (app4) |

- **`access_token`**: treat as an opaque credential — forward it unchanged to the FHIR server in the `Authorization: Bearer` header. Do not decode it or build logic on its internal structure; only the resource server is expected to interpret it.
- **`id_token`**: meant to be decoded by the application to learn who logged in. Its payload contains standard OIDC identity claims (`sub`, `fhirUser`, etc.). app4 decodes it server-side to populate the ID Token dialog.

### Using the access_token for FHIR API calls

Every FHIR R4 API call must include the access_token as a **Bearer token** in the `Authorization` header:

```typescript
const fhirResponse = await fetch(`${config.epicFhirBaseUrl}/Patient`, {
  headers: {
    Authorization: `Bearer ${entry.accessToken}`,  // the JWT string is the credential
    Accept: 'application/fhir+json',               // FHIR R4 MIME type
  },
})
```

Epic's FHIR server receives the Bearer token, verifies its RS256 signature against Epic's JWKS endpoint, checks that it has not expired, and confirms the requested resource falls within the granted scope. app4 never needs to validate the JWT — that is the resource server's responsibility.

### Decoding a JWT for inspection (without verification)

The payload segment of a JWT is Base64URL-encoded JSON — no key is required to read it. Decoding is used for display purposes only (the ID Token dialog):

```typescript
// src/lib/jwt.ts

export function decodeJwtPayload(token: string): Record<string, unknown> | null {
  try {
    const payloadB64 = token.split('.')[1]
    // Buffer.from with 'base64url' handles padding and character substitution automatically.
    // Available in Bun natively (Node.js-compatible API).
    return JSON.parse(Buffer.from(payloadB64, 'base64url').toString('utf8'))
  } catch {
    return null
  }
}
```

This decodes but does **not** verify the signature. The token was received from Epic over a TLS-secured back-channel during the OAuth callback, so its authenticity is established by transport security. This function is for display only — never use unverified JWT claims for authorization decisions.

**To inspect a JWT in a browser**: paste the full token at [jwt.io](https://jwt.io) to see the decoded header, payload, and signature.

---

## ID Token Dialog

When the `openid` scope is granted, Epic returns an `id_token` alongside the `access_token`. The `id_token` is an OIDC JWT containing identity claims about the authenticated user — not a credential for API calls, but an assertion of who logged in.

app4 stores the `id_token` in the server-side `tokenStore` and decodes it at every home page load to populate an "ID Token" button and `<dialog>` modal. Clicking the button opens the modal showing the decoded JWT payload.

```tsx
// In src/views/Home.tsx — render only when idTokenClaimsJson is not null
{idTokenClaimsJson && (
  <>
    <button
      className="btn btn--secondary"
      onclick="document.getElementById('id-token-dialog').showModal()"
    >
      ID Token
    </button>

    <dialog
      id="id-token-dialog"
      onclick="if (event.target === this) this.close()"
    >
      <div className="dialog-header">
        <h2>OpenID Connect ID Token</h2>
        <button
          className="dialog-close"
          onclick="this.closest('dialog').close()"
          aria-label="Close dialog"
        >
          &times;
        </button>
      </div>
      <div className="dialog-body">
        <p className="dialog-subtitle">
          Decoded JWT payload &mdash; identity claims returned by Epic
        </p>
        <pre
          className="fhir-json"
          dangerouslySetInnerHTML={{ __html: idTokenClaimsJson }}
        />
      </div>
    </dialog>
  </>
)}
```

Three ways to close the dialog:
1. **× button** — `onclick` calls `this.closest('dialog').close()`
2. **ESC key** — native browser behavior built into `<dialog>`, no code required
3. **Backdrop click** — the `onclick` on `<dialog>` checks `event.target === this`; a click landing on the dialog element itself (outside the content box) closes it

`showModal()` opens the dialog as a modal: centered on the page, a `::backdrop` overlay dims the background, and focus is trapped inside until it is closed. All handled by the browser natively.

**`dangerouslySetInnerHTML`** is Hono JSX's equivalent of Jinja2's `| safe` filter. Use it only for trusted, server-controlled content. `idTokenClaimsJson` is produced by `JSON.stringify()` from a dict decoded from Epic's HTTPS token endpoint — no user input is in the path.

---

## Patient Portal: HTMX Fragments from Hono

The patient portal page is static Hono JSX (server-rendered on initial load). HTMX buttons trigger `GET /fhir/*` requests. Hono returns HTML fragments. HTMX injects them into `#result`. No client-side JavaScript beyond the HTMX CDN script.

### Portal page (src/views/Patient.tsx)

```tsx
import type { FC } from 'hono/jsx'
import { Layout } from './Layout'

const Patient: FC = () => (
  <Layout title="Patient Portal">
    <div className="portal-header">
      <h1>Patient Portal</h1>
      <a href="/" className="btn btn--secondary">Home</a>
    </div>
    <hr />
    <div className="action-row">
      <button
        className="btn btn--special"
        hx-get="/fhir/medication"
        hx-target="#result"
        hx-swap="innerHTML"
        hx-indicator="#fhir-loading"
        hx-disabled-elt="this"
      >Patient Summary</button>

      <button
        className="btn"
        hx-get="/fhir/patient"
        hx-target="#result"
        hx-swap="innerHTML"
        hx-indicator="#fhir-loading"
        hx-disabled-elt="this"
      >GET /Patient</button>

      <button
        className="btn"
        hx-get="/fhir/medication"
        hx-target="#result"
        hx-swap="innerHTML"
        hx-indicator="#fhir-loading"
        hx-disabled-elt="this"
      >GET /MedicationRequest</button>

      <button
        className="btn"
        hx-get="/fhir/labreport"
        hx-target="#result"
        hx-swap="innerHTML"
        hx-indicator="#fhir-loading"
        hx-disabled-elt="this"
      >GET /LabReports</button>

      <button
        className="btn"
        hx-get="/fhir/vitalsigns"
        hx-target="#result"
        hx-swap="innerHTML"
        hx-indicator="#fhir-loading"
        hx-disabled-elt="this"
      >GET /VitalSigns</button>

      <span id="fhir-loading" className="htmx-indicator fhir-loading">Loading&hellip;</span>
    </div>
    <hr />
    <main>
      <div id="result"></div>
    </main>
  </Layout>
)

export default Patient
```

### FHIR fragment endpoint pattern

All four FHIR endpoints share this helper and follow the same six steps:

```typescript
// src/routes/fhir.ts

import { Hono } from 'hono'
import { tokenStore } from '../lib/tokenStore'
import { config } from '../config'

export const fhir = new Hono()

// Shared error helper — returns HTTP 200 with styled error HTML so HTMX can inject it
function errorHtml(message: string, detail: string = ''): string {
  const detailBlock = detail
    ? `<pre class="fhir-error-detail">${detail}</pre>`
    : ''
  return `<p class="fhir-error">${message}</p>${detailBlock}`
}
```

The six-step pattern for `GET /fhir/patient`:

```typescript
fhir.get('/patient', async (c) => {
  // Step 1 — Read session ID
  const session = c.get('session')
  const sessionId = await session.get('sessionId') as string | undefined
  if (!sessionId) {
    return c.html(errorHtml('No active session. <a href="/auth/login">Connect to Epic Sandbox</a> first.'))
  }

  // Step 2 — Look up access token from server-side store
  const entry = tokenStore.get(sessionId)
  if (!entry?.accessToken) {
    return c.html(errorHtml('Session token not found — the server may have restarted. <a href="/auth/login">Reconnect</a>.'))
  }

  // Step 3 — Check token expiry
  const tokenExpiresAt = await session.get('tokenExpiresAt') as string | undefined
  if (tokenExpiresAt && Date.now() >= new Date(tokenExpiresAt).getTime()) {
    return c.html(errorHtml('Access token has expired. <a href="/auth/login">Reconnect to Epic Sandbox</a>.'))
  }

  // Step 4 — Call Epic FHIR with Bearer token
  let fhirResponse: Response
  try {
    fhirResponse = await fetch(`${config.epicFhirBaseUrl}/Patient`, {
      headers: {
        Authorization: `Bearer ${entry.accessToken}`,
        Accept: 'application/fhir+json',
      },
    })
  } catch (err) {
    return c.html(errorHtml(`Network error contacting Epic FHIR: ${err}`))
  }

  // Step 5 — Handle non-2xx responses
  if (!fhirResponse.ok) {
    const detail = await fhirResponse.text()
    return c.html(errorHtml(`Epic FHIR returned HTTP ${fhirResponse.status}.`, detail))
  }

  // Step 6 — Format and return the HTML fragment
  const bundle = await fhirResponse.json()
  const formatted = JSON.stringify(bundle, null, 2)
  return c.html(`<pre class="fhir-json">${formatted}</pre>`)
})
```

---

## GET /MedicationRequest

### Why a patient ID is required

`GET /Patient` uses a special `me` context — Epic automatically scopes it to the patient associated with the OAuth session. `MedicationRequest` has no such shortcut. It is always a search against a specific patient:

```
GET /MedicationRequest?patient=<fhir_patient_id>
```

Without the `patient` parameter, Epic rejects the request.

### Where the patient ID comes from

Epic includes a `patient` field in the token response for patient-scoped standalone launches. The value is the FHIR ID of the in-context patient. app4 captures it during `/auth/callback` and stores it in the `tokenStore`:

```typescript
tokenStore.set(sessionId, {
  // ...
  patientId: tokenData.patient ?? '',  // empty string if launch was not patient-scoped
})
```

If `patientId` is empty — which happens when the launch was not patient-scoped (e.g., a provider login without selecting a specific patient) — the handler returns an informative error fragment rather than making a doomed API call.

### Scope and app registration requirements

Two things must be in place for MedicationRequest calls to succeed:

1. **`MedicationRequest.Read (R4)`** capability must be enabled in the Epic developer portal app registration
2. **`patient/MedicationRequest.read`** should be included in `EPIC_SCOPE` (in the sandbox this is not strictly enforced, but it is required in production)

### Route implementation (insert between Step 2 and Step 3)

```typescript
fhir.get('/medication', async (c) => {
  // Steps 1-2: same as GET /patient ...

  // Step 2a — Check for patient ID (required for MedicationRequest)
  const patientId = entry.patientId
  if (!patientId) {
    return c.html(errorHtml(
      'No patient ID in session. MedicationRequest requires a patient-scoped launch. ' +
      'Ensure the <code>launch/patient</code> scope is included and ' +
      '<a href="/auth/login">reconnect to Epic Sandbox</a>.'
    ))
  }

  // Steps 3-5: same as GET /patient ...

  // Step 4 — Call Epic FHIR with patient parameter
  fhirResponse = await fetch(`${config.epicFhirBaseUrl}/MedicationRequest`, {
    // URLSearchParams serializes ?patient=<id> and handles encoding
    ...
    // headers same as GET /patient
  })

  // Steps 5-6: same as GET /patient ...
})
```

Use `URLSearchParams` to serialize the query parameter:
```typescript
const params = new URLSearchParams({ patient: patientId })
const url = `${config.epicFhirBaseUrl}/MedicationRequest?${params}`
```

---

## GET /Observation: Lab Reports and Vital Signs

### The Observation resource

`Observation` is FHIR's catch-all resource for clinical measurements and findings. A single resource type covers lab results, vital signs, SDOH questionnaire responses, and more. The resource has a consistent structure regardless of what kind of measurement it contains:

```json
{
  "resourceType": "Observation",
  "status": "final",
  "category": [{ "coding": [{ "code": "vital-signs" }] }],
  "code": { "coding": [{ "system": "http://loinc.org", "code": "8867-4", "display": "Heart rate" }] },
  "subject": { "reference": "Patient/abc123" },
  "effectiveDateTime": "2024-03-15T10:30:00Z",
  "valueQuantity": { "value": 72, "unit": "beats/minute" }
}
```

### The category system

Because Observation covers so many domains, filtering by `category` is essential. The standard category system is `http://terminology.hl7.org/CodeSystem/observation-category`:

| Code | Domain | Examples |
|---|---|---|
| `laboratory` | Lab results | CBC, metabolic panel, urinalysis |
| `vital-signs` | Vital sign measurements | Blood pressure, heart rate, temperature, height, weight |
| `survey` | Questionnaire responses | SDOH assessments, PHQ-9, GAD-7 |

### Why both endpoints use `GET /Observation`

Lab reports and vital signs share a single FHIR resource type. The only difference between the two FHIR calls is the `category` query parameter:

```
GET /Observation?patient=<id>&category=laboratory    → lab results Bundle
GET /Observation?patient=<id>&category=vital-signs   → vital signs Bundle
```

Both route handlers in `src/routes/fhir.ts` follow the identical six-step pattern as MedicationRequest. The only structural difference is the category value in Step 4:

```typescript
// Lab reports
const params = new URLSearchParams({ patient: patientId, category: 'laboratory' })

// Vital signs
const params = new URLSearchParams({ patient: patientId, category: 'vital-signs' })

const url = `${config.epicFhirBaseUrl}/Observation?${params}`
```

Both endpoints also require a patient ID check (same as MedicationRequest).

### Scope requirements and category-specific grants

Epic registers Observation access per category (see **API Capabilities** in the Epic registration section). Each enabled category appears as a separate scope entry in the token response using SMART v2's parameterized scope format:

```
patient/Observation.r?category=http://terminology.hl7.org/CodeSystem/observation-category|laboratory
patient/Observation.r?category=http://terminology.hl7.org/CodeSystem/observation-category|vital-signs
```

Epic enforces these independently: a token with `laboratory` grant but not `vital-signs` will succeed on lab requests and return 403 on vital signs requests. **Diagnosing a 403**: check the Scope row on the home page after reconnecting. If only one category appears in the scope string, the other capability is not yet registered in the portal.

### Result volume and pagination

Observation bundles can be large — a patient with years of clinical history may have hundreds of results. To limit results, add `_count` as a third parameter:

```typescript
const params = new URLSearchParams({ patient: patientId, category: 'laboratory', _count: '20' })
```

When more results exist beyond `_count`, Epic includes a `link` array in the Bundle with a `next` relation URL for the next page. app4 does not currently implement pagination — the full result set is returned. This is sufficient for development against the sandbox test patient, whose history is limited.

**Empty bundles are valid**: if the sandbox test patient has no recorded lab results or vital signs, Epic returns HTTP 200 with `"total": 0` and an empty `entry` array. The handler formats and returns this normally — the `<pre>` block will show the empty Bundle structure. This is correct behavior, not an error.

---

## Session Management

### Session data written to the cookie

app4 stores only lightweight metadata in the encrypted session cookie — never the access token or any sensitive credential:

```
Session cookie (encrypted, ~300 bytes total):
{
  sessionId:      "a3f9e1..."   // 32-char hex key into tokenStore
  tokenExpiresAt: "2026-06-17T14:30:00.000Z"  // ISO 8601 — same format as app2
  scope:          "openid fhirUser patient/Patient.r"
  oauthState:     "abc..."      // present only during the login flow; cleared on callback
}
```

### Session cookie security properties

| Property | Value | Reason |
|---|---|---|
| `httpOnly: true` | Cookie not accessible from JavaScript | Prevents XSS from reading the session ID |
| `sameSite: 'Lax'` | Cookie sent on same-site requests and top-level cross-site GET | Allows Epic's redirect to deliver the cookie |
| `secure: false` (dev) | Cookie sent over HTTP | Changed to `true` in production (requires HTTPS) |
| AES-GCM encryption | Payload is ciphertext | Cookie content is unreadable without the secret key |

**`SameSite=Lax`** allows the browser to send the session cookie on top-level cross-site GET navigations (needed for Epic's redirect back to the callback URL) while blocking it on cross-site subrequests (CSRF protection for state-changing operations).

### Accessing the session in route handlers

```typescript
const session = c.get('session')

// Read a value (returns unknown — cast to the expected type)
const sessionId = await session.get('sessionId') as string | undefined

// Write a value
await session.set('tokenExpiresAt', expiresAt.toISOString())

// Destroy the session (logout)
await session.deleteSession()
```

All operations are `async` — the `await` is required because `CookieStore` performs crypto operations.

---

## TypeScript Configuration for Hono JSX

The `tsconfig.json` must be configured to use Hono's JSX factory instead of React's. Without this, TypeScript errors on JSX syntax in `.tsx` files:

```json
{
  "compilerOptions": {
    "target": "ESNext",
    "module": "ESNext",
    "moduleResolution": "bundler",
    "strict": true,
    "jsx": "react-jsx",
    "jsxImportSource": "hono/jsx",
    "types": ["bun-types"]
  }
}
```

**Key settings:**

- **`"jsx": "react-jsx"`**: uses the modern JSX transform (no manual `import React` in every file)
- **`"jsxImportSource": "hono/jsx"`**: tells the transform to import JSX runtime from `hono/jsx` instead of `react` — this is what makes `<div>` call Hono's renderer, not React's
- **`"types": ["bun-types"]`**: adds Bun-specific type definitions (`Bun.serve()`, etc.)

With this configuration, all `.tsx` files automatically use Hono's JSX renderer. No per-file pragma (`/** @jsxImportSource hono/jsx */`) is needed.

---

## Key Routes

| Method | Path | Description |
|---|---|---|
| `GET` | `/` | Home page — session status or login prompt |
| `GET` | `/auth/login` | Builds Epic authorization URL and redirects |
| `GET` | `/auth/callback` | Receives code; exchanges for token; sets session |
| `GET` | `/auth/logout` | Clears session cookie; removes token store entry |
| `GET` | `/patient` | Patient portal page — HTMX-wired portal UI |
| `GET` | `/fhir/patient` | HTMX — calls `GET /Patient`; returns HTML fragment |
| `GET` | `/fhir/medication` | HTMX — calls `GET /MedicationRequest?patient=<id>`; returns HTML fragment |
| `GET` | `/fhir/labreport` | HTMX — calls `GET /Observation?patient=<id>&category=laboratory`; returns HTML fragment |
| `GET` | `/fhir/vitalsigns` | HTMX — calls `GET /Observation?patient=<id>&category=vital-signs`; returns HTML fragment |
| `GET` | `/health` | System health check |

Route paths are identical to app2. The HTMX `hx-get` attribute values in the portal do not change between app2 and app4 (except for the absence of an `/api/` prefix).

---

## Running app4

From the `app4/` directory:

```bash
bun run dev
```

This runs `bun run --hot src/index.ts`. The `--hot` flag enables hot module replacement. Open `http://localhost:8004`.

For a one-time run without hot reload:
```bash
bun run start
```

**No build step.** There is no compilation phase. Bun reads and executes `.ts` files directly.

**TypeScript type checking** (optional — does not affect running):
```bash
bunx tsc --noEmit
```

Bun does not enforce types at runtime — it strips type annotations. Use `tsc --noEmit` to find type errors without generating output files.

---

## Development Setup: Phases and Steps

---

### Phase 0: Environment Setup

#### Step 0.1 — Install Bun

```bash
curl -fsSL https://bun.sh/install | bash

# Restart your terminal (the installer updates ~/.zshrc)
source ~/.zshrc

# Verify
bun --version   # should print 1.x.x
```

Bun installs a single binary at `~/.bun/bin/bun` and adds it to `PATH`. No version manager is required.

#### Step 0.2 — Create the app4 project

From the `fhir-bootcamp/` project root:

```bash
mkdir app4
cd app4
bun init
```

`bun init` prompts for:
- **Package name**: `app4`
- **Entry point**: `src/index.ts`

Accept both defaults. It creates `package.json`, `tsconfig.json`, `.gitignore`, and `src/index.ts`.

#### Step 0.3 — Install dependencies

```bash
bun add hono hono-sessions
bun add -d @types/bun
```

Verify `package.json` shows `hono` and `hono-sessions` under `dependencies`, and `@types/bun` under `devDependencies`.

#### Step 0.4 — Configure TypeScript

Replace the generated `tsconfig.json` with the configuration from the **TypeScript Configuration for Hono JSX** section above.

#### Step 0.5 — Create directory structure

```bash
mkdir -p src/lib src/routes src/views public/css public/images
```

#### Step 0.6 — Configure package.json scripts

```json
{
  "scripts": {
    "dev": "bun run --hot src/index.ts",
    "start": "bun run src/index.ts"
  }
}
```

#### Step 0.7 — Create `.env.local`

Create `app4/.env.local` with the contents from the **Environment Variables** section.

Generate the session secret:
```bash
bun -e "console.log(require('crypto').randomBytes(32).toString('hex'))"
```

#### Step 0.8 — Update Epic app registration

Add `http://localhost:8004/auth/callback` as a redirect URI to the existing Epic sandbox app registration, or create a new app. See the **Epic Sandbox App Registration** section.

#### Step 0.9 — Verify the skeleton

Replace the generated `src/index.ts` with:

```typescript
import { Hono } from 'hono'

const app = new Hono()
app.get('/', (c) => c.text('app4 is running'))

export default { port: 8004, fetch: app.fetch }
```

Run and verify:
```bash
bun run dev
# Open http://localhost:8004 — should display "app4 is running"
```

Press Ctrl-C to stop.

---

### Phase 1: Project Foundation

#### Step 1.1 — Create `src/config.ts`

Read environment variables and export a typed config object. Throw at startup if required variables are missing:

```typescript
function requireEnv(name: string): string {
  const value = process.env[name]
  if (!value) throw new Error(`Missing required environment variable: ${name}`)
  return value
}

export const config = {
  appName:          process.env.APP_NAME ?? 'FHIR Bootcamp - app4',
  appPort:          Number(process.env.APP_PORT ?? 8004),
  sessionSecretKey: requireEnv('SESSION_SECRET_KEY'),
  epicClientId:     requireEnv('EPIC_NONPROD_CLIENT_ID'),
  epicClientSecret: requireEnv('EPIC_CLIENT_SECRET'),
  epicAuthorizeUrl: requireEnv('EPIC_AUTHORIZE_URL'),
  epicTokenUrl:     requireEnv('EPIC_TOKEN_URL'),
  epicFhirBaseUrl:  requireEnv('EPIC_FHIR_BASE_URL'),
  epicScope:        process.env.EPIC_SCOPE ?? 'openid fhirUser',
  appRedirectUri:   requireEnv('APP_REDIRECT_URI'),
}
```

#### Step 1.2 — Create `src/lib/tokenStore.ts`

The in-memory token store. See the **Token Store** section for the full implementation.

#### Step 1.3 — Create `src/lib/jwt.ts`

The `decodeJwtPayload` function. See **Decoding a JWT for inspection** in the JWT section.

#### Step 1.4 — Create `src/views/Layout.tsx`

The base HTML shell. Responsibilities:
- `<html>`, `<head>`, `<body>` wrapper
- `<title>` from a prop
- `<link>` to `/static/css/main.css`
- HTMX `<script>` CDN tag
- Font Awesome CDN `<script>` tag (if using icons)
- `{children}` slot for page content

#### Step 1.5 — Copy and adapt CSS

Copy `app2/static/css/main.css` to `app4/public/css/main.css`. All existing CSS classes (`.fhir-json`, `.fhir-error`, `.btn`, `.card`, `.htmx-indicator`, dialog styles) are directly reusable.

#### Step 1.6 — Wire up `src/index.ts`

```typescript
import { Hono } from 'hono'
import { serveStatic } from 'hono/bun'
import { sessionMiddleware, CookieStore } from 'hono-sessions'
import { config } from './config'

const app = new Hono()

// Session middleware — must be applied before any route that reads the session
app.use('*', sessionMiddleware({
  store: new CookieStore(),
  encryptionKey: config.sessionSecretKey,
  expireAfterSeconds: 3600,
  cookieOptions: {
    name: 'app4_session',
    sameSite: 'Lax',
    httpOnly: true,
    secure: false,
  },
}))

// Serve static files from public/ at /static/*
app.use('/static/*', serveStatic({ root: './public' }))

// Route modules — uncomment as phases are completed
// import { auth } from './routes/auth'
// import { pages } from './routes/pages'
// import { fhir } from './routes/fhir'
// app.route('/auth', auth)
// app.route('/', pages)
// app.route('/fhir', fhir)

export default { port: config.appPort, fetch: app.fetch }
```

---

### Phase 2: OAuth Flow

Create `src/routes/auth.ts` with `export const auth = new Hono()` and three routes. Mount in `src/index.ts` with `app.route('/auth', auth)` after uncommenting the import.

#### Step 2.1 — `GET /auth/login`

Implement using the pattern from **Step 1 — Login redirect** in the OAuth section. When complete, visit `http://localhost:8004/auth/login` — you should be redirected to Epic's login page.

#### Step 2.2 — `GET /auth/callback`

The most complex handler. Implement the full code from **Step 3 — Token exchange**. Debug with `console.log(tokenData)` — output appears in the terminal where `bun run dev` is running.

After implementation, complete the full Epic login flow and confirm:
- The terminal shows the token data log output
- The browser shows the meta-refresh page for one second
- The browser navigates to `/` (minimal response until Phase 3)

#### Step 2.3 — `GET /auth/logout`

The simplest handler: read session ID, delete from `tokenStore`, call `session.deleteSession()`, redirect to `/`.

---

### Phase 3: Home Page

#### Step 3.1 — Create `src/views/Home.tsx`

Props needed:
- `sessionActive: boolean`
- `tokenExpired: boolean`
- `expiresDisplay: string`
- `scope: string`
- `idTokenClaimsJson: string | null`

Two conditional sections:
- **Unauthenticated**: connect prompt + `<a href="/auth/login">Connect to Epic Sandbox</a>`
- **Authenticated**: session metadata card + Disconnect / ID Token / Portal buttons

Include the ID Token `<dialog>` from the **ID Token Dialog** section, wrapped in `{idTokenClaimsJson && (...)}`.

#### Step 3.2 — Create `src/routes/pages.ts` with `GET /`

```typescript
import { Hono } from 'hono'
import { tokenStore } from '../lib/tokenStore'
import { decodeJwtPayload } from '../lib/jwt'
import Home from '../views/Home'

export const pages = new Hono()

pages.get('/', async (c) => {
  const session = c.get('session')
  const sessionId = await session.get('sessionId') as string | undefined
  const tokenExpiresAt = await session.get('tokenExpiresAt') as string | undefined
  const scope = await session.get('scope') as string | undefined

  const sessionActive = !!sessionId
  let tokenExpired = false
  let expiresDisplay = ''

  if (tokenExpiresAt) {
    const expiresAt = new Date(tokenExpiresAt)
    tokenExpired = Date.now() >= expiresAt.getTime()
    expiresDisplay = expiresAt.toLocaleString('en-US', {
      month: 'short', day: 'numeric', year: 'numeric',
      hour: 'numeric', minute: '2-digit', timeZone: 'UTC', timeZoneName: 'short'
    })
  }

  let idTokenClaimsJson: string | null = null
  if (sessionId) {
    const entry = tokenStore.get(sessionId)
    if (entry?.idToken) {
      const claims = decodeJwtPayload(entry.idToken)
      if (claims) idTokenClaimsJson = JSON.stringify(claims, null, 2)
    }
  }

  return c.html(
    <Home
      sessionActive={sessionActive}
      tokenExpired={tokenExpired}
      expiresDisplay={expiresDisplay}
      scope={scope ?? ''}
      idTokenClaimsJson={idTokenClaimsJson}
    />
  )
})
```

Mount in `src/index.ts`: `app.route('/', pages)`

---

### Phase 4: Patient Portal

#### Step 4.1 — Add `GET /patient` to `src/routes/pages.ts`

```typescript
import Patient from '../views/Patient'

pages.get('/patient', (c) => c.html(<Patient />))
```

#### Step 4.2 — Create `src/routes/fhir.ts`

Implement four handlers following the six-step pattern from **Patient Portal: HTMX Fragments from Hono**:

- `fhir.get('/patient', ...)` — calls `GET /Patient`
- `fhir.get('/medication', ...)` — calls `GET /MedicationRequest?patient=<id>` (includes patient ID check)
- `fhir.get('/labreport', ...)` — calls `GET /Observation?patient=<id>&category=laboratory` (includes patient ID check)
- `fhir.get('/vitalsigns', ...)` — calls `GET /Observation?patient=<id>&category=vital-signs` (includes patient ID check)

All four share the `errorHtml` helper. Mount in `src/index.ts`: `app.route('/fhir', fhir)`

#### Step 4.3 — Create `src/views/Patient.tsx`

The full portal page from **Patient Portal: HTMX Fragments from Hono** → **Portal page**.

---

### Phase 5: Polish and Verification

#### Step 5.1 — Health check route

Add to `src/routes/pages.ts` or `src/index.ts`:

```typescript
app.get('/health', (c) => c.json({
  appName: config.appName,
  status: 'healthy',
  environment: process.env.APP_ENV ?? 'development',
}))
```

#### Step 5.2 — TypeScript type check

```bash
bunx tsc --noEmit
```

Fix all type errors before proceeding.

#### Step 5.3 — End-to-end test

Test the complete application flow in order:

1. **Unauthenticated home page**: visit `http://localhost:8004` — confirm the connect prompt renders and the "Connect to Epic Sandbox" button is visible
2. **Login redirect**: click "Connect to Epic Sandbox" — confirm the browser redirects to Epic's login page (`fhir.epic.com`)
3. **Epic login**: log in with Epic sandbox credentials and approve the consent screen — confirm the browser redirects back to app4
4. **Authenticated home page**: confirm the session card renders with expiration time, granted scopes, and a note that the token is stored server-side
5. **ID Token modal**: click "ID Token" — confirm the dialog opens with decoded JWT claims; close with the × button, ESC key, and backdrop click
6. **Portal navigation**: click "Portal" — confirm navigation to `http://localhost:8004/patient`
7. **GET /Patient**: click the button — confirm a FHIR Bundle JSON appears in `#result`; confirm the button was disabled during the request; confirm the loading indicator appeared
8. **GET /MedicationRequest**: click the button — confirm medication data (or a clear error if the patient scope is absent)
9. **GET /LabReports**: click the button — confirm lab results or a scope error
10. **GET /VitalSigns**: click the button — confirm vital signs or a scope error
11. **Hot reload**: edit a route handler (e.g., change a log statement) — confirm Bun reloads the module and the session cookie still works (token store is preserved)
12. **Logout**: navigate to the home page, click "Disconnect" — confirm the session is cleared and the page reverts to the unauthenticated state
13. **Post-logout FHIR call**: click "Portal" again after logout and click any FHIR button — confirm the "No active session" error appears in `#result`

---

## Best Practices for This Stack

### `bun run --hot` preserves in-memory state

Unlike `--watch` (which kills and restarts the process) or Python's `uvicorn --reload`, Bun's `--hot` reloads only changed modules. The `tokenStore` Map survives file saves during development — you can edit route handlers mid-session without losing your OAuth token.

### Use `c.html()` for fragments, JSX components for full pages

For short HTMX fragments (error messages, `<pre>` blocks), return a template string with `c.html('<pre>...</pre>')`. Reserve Hono JSX components (`<Home />`, `<Patient />`) for full pages where the component structure provides value.

### `onclick` uses HTML attribute syntax

Use lowercase `onclick`, `onchange`, etc. in Hono JSX (not camelCase `onClick`). Hono JSX outputs HTML strings — the attributes land in the browser as raw HTML. React's `onClick` does not exist here.

### `fetch()` does not throw on HTTP errors

`fetch()` throws only for network-level failures (DNS failure, connection refused, timeout). A 401 or 403 from Epic is a successful `fetch()` call — `fhirResponse.ok` is `false`, but no exception is thrown. Always check `fhirResponse.ok` before calling `.json()`:

```typescript
if (!fhirResponse.ok) {
  const detail = await fhirResponse.text()  // safe: .text() works on any response
  return c.html(errorHtml(`Epic returned ${fhirResponse.status}`, detail))
}
const bundle = await fhirResponse.json()  // safe: we know it's a 2xx JSON response
```

### Return error HTML at HTTP 200 from HTMX endpoints

HTMX does not swap response bodies with non-2xx status codes. All error paths in FHIR handlers must return HTTP 200 with styled error HTML via the `errorHtml()` helper.

### Keep route handlers thin

Route handlers read inputs, call helpers, return responses. Logic belongs in `src/lib/`. The `errorHtml` helper and `decodeJwtPayload` function are examples of this separation.

---

## Comparison: app2, app3, and app4

| | app2 (FastAPI + HTMX) | app3 (Next.js + React) | app4 (Hono + HTMX) |
|---|---|---|---|
| **Language** | Python | TypeScript | TypeScript |
| **Rendering** | Server (Jinja2) | Server (RSC) + Client (React) | Server (Hono JSX) |
| **Interactivity** | HTMX fragments | React `useState` + `fetch` | HTMX fragments |
| **HTTP client** | `httpx` | `fetch` | `fetch` |
| **Session** | Signed cookie | Encrypted cookie | Encrypted cookie |
| **Build step** | None | `next build` | None |
| **Client JS bundle** | None (HTMX via CDN) | React + Next.js runtime | None (HTMX via CDN) |
| **Architectural similarity to app2** | — | Low | Very high |
| **TypeScript** | No | Yes | Yes |

app4 is the TypeScript translation of app2. The architecture, rendering model, and interactivity pattern are preserved. The implementation language and framework are modernized.

---

## Production Considerations

- **Replace `tokenStore` with Redis**: the in-memory Map is cleared on process restart and is not shared across multiple Bun instances. Use `ioredis` for a Redis-backed store
- **Set `secure: true`** on the session cookie in production (requires HTTPS at the origin)
- **Update `APP_REDIRECT_URI`** to the production HTTPS callback URL and register it in Epic
- **Use `bun run start`** in production (`--hot` is for development only); run the process under a supervisor (systemd, PM2)
- **Reverse proxy**: place nginx or Caddy in front of Bun for TLS termination. Bun's HTTP server is production-capable but does not handle TLS directly
- **Store `SESSION_SECRET_KEY` in a secrets manager**, not in `.env.local`. Inject via environment at deploy time
