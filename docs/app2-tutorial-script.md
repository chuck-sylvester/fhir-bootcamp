# app2 Tutorial — Presenter Script

**Presentation**: Building a SMART on FHIR Application with FastAPI + HTMX + Jinja2 + HTTPX  
**Target audience**: Python developers with limited FHIR experience  
**Format**: Full technical tutorial, introductory through advanced  
**Companion file**: `docs/app2-tutorial.pptx`

Slide numbers in headings correspond directly to slides in the PPTX.

---

## Slide 1 — Title

Welcome, everyone. In this tutorial we're going to build a real, working application that connects to Epic's FHIR API using Python. By the end you'll understand not just what the code does, but why every design decision was made — from the choice of tech stack to the way we store session tokens.

The application is called app2, part of the fhir-bootcamp repository. It's a full server-side rendered web app built with FastAPI, HTMX, and Jinja2. It authenticates via OAuth 2.0, talks to Epic's sandbox FHIR API, and displays patient data — medications, lab results, vital signs — without a single JavaScript framework.

Let's get started.

---

## SECTION 1 — Introduction

---

## Slide 2 — What We're Building

Before we touch any code, let me describe exactly what the application does so you have a mental model to hang everything on.

The user opens the app and sees a single button: "Connect to Epic Sandbox." Clicking that kicks off an OAuth 2.0 login with Epic. After the user authenticates, they're brought back to the home page which now shows their session status, the granted scopes, and the token expiry time. There's also an ID Token button that opens a modal showing the decoded OIDC identity claims — we'll explain what that means later.

From the home page, the user can navigate to a Patient Portal. That portal has five buttons, each of which makes a live FHIR API call to Epic and displays the raw FHIR JSON response inline on the page — no reload, no page navigation. We're querying Patient demographics, MedicationRequest, and two variants of Observation: one for lab results and one for vital signs.

All of this happens with no JavaScript framework. The interactivity comes from HTMX, which is a single CDN script tag.

---

## Slide 3 — Prerequisites

This tutorial is designed for Python developers with some web development experience. You don't need to know anything about FHIR, OAuth, or healthcare IT — we'll introduce those concepts from scratch.

You should be comfortable with Python's async/await syntax, at least conceptually. You should have done basic web development — either FastAPI, Flask, or Django. You need to understand HTTP fundamentals: what a GET request is, what a header is, what a status code is, what a cookie is. And you should be able to read and write basic HTML and CSS.

That's it. No healthcare domain knowledge required.

---

## Slide 4 — Repository Structure

The fhir-bootcamp repository is organized so that each application is in its own top-level folder — app1, app2, and so on. Each is built independently. There are three shared files at the root: the virtual environment, requirements.txt, and .env. Every app reads its configuration from that shared .env file.

Inside app2 you have main.py, config.py, and an __init__.py. The routers folder has auth.py for OAuth routes and pages.py for the UI and FHIR routes. Templates and static files live in their respective folders. And services contains a standalone script that was used for early experimentation.

There's also a docs folder with app2-guide.md — a very detailed developer guide that documents every step, every design decision, and every line of reasoning. If this tutorial moves too fast on any topic, that guide has the full depth.

---

## Slide 5 — How to Follow Along

Here's how to get the application running. The complete detailed steps are in app2-guide.md, but the essential path is: clone the repo, create a Python 3.12 virtual environment, install dependencies, and then register a free developer app at open.epic.com.

The Epic registration is the only step that requires external setup. It's free, takes about five minutes, and you'll get a Client ID and Client Secret that go into your .env file. Once that's done, run uvicorn from the project root — always from the root, not from inside the app2 folder — and open localhost:8000 in a browser.

---

## SECTION 2 — FHIR Fundamentals

---

## Slide 6 — What is FHIR?

FHIR stands for Fast Healthcare Interoperability Resources. It's a specification from HL7 — the standards body for healthcare IT — that defines a REST API for exchanging health information. R4, Release 4, is the current stable version and the one this tutorial uses.

Why does FHIR matter right now? In 2021, a US federal rule called the 21st Century Cures Act required that all certified EHR vendors expose FHIR R4 APIs for patient data access. That means every major US hospital system is now required to have a FHIR API. Epic, Oracle Cerner, Microsoft Azure Health Data Services, Google Cloud Healthcare API — they all implement FHIR R4.

The exciting thing about FHIR is portability. Once you know the FHIR API and understand SMART on FHIR authentication, you can query any compliant system using the same patterns. The code you write against Epic's sandbox will work, with minimal changes, against Cerner.

---

## Slide 7 — FHIR Resources: The Data Model

In FHIR, every piece of clinical information is represented as a Resource. A Resource is a structured JSON object — it has a specific shape, specific required and optional fields, and a standardized way of referencing other resources.

The resources we'll use in app2 are Patient, MedicationRequest, and Observation. Patient holds demographics — name, date of birth, gender, address. MedicationRequest represents a prescription or medication order. Observation is a catch-all for clinical measurements: lab results, vital signs, questionnaire responses — we'll go deep on Observation later because it has an important nuance.

Other common resources you'll encounter but that aren't in app2 yet include Condition for diagnoses, Encounter for visits, and Practitioner for clinicians.

---

## Slide 8 — FHIR R4 REST API Conventions

The FHIR R4 API is a REST API. The base URL for Epic's sandbox is long but consistent. All FHIR calls go to that base URL followed by the resource type.

There are two main interaction patterns. A "read" retrieves a specific resource by its ID — that's a GET to /ResourceType/{id}. A "search" retrieves a set of matching resources — that's a GET to /ResourceType with query parameters. Searches return a Bundle, which is itself a FHIR resource that wraps a list of matching results in an entry array.

The Accept header you should send is application/fhir+json — that's the FHIR-specific MIME type. Epic also accepts application/json, but the FHIR type is preferred and signals that you understand the protocol.

---

## Slide 9 — SMART on FHIR

SMART stands for Substitutable Medical Apps Reusable Technologies. It's a set of specifications built on top of FHIR that defines how apps get permission to access patient data.

The core of SMART on FHIR is OAuth 2.0 with OpenID Connect layered on top. It defines specific OAuth scopes that map to FHIR resource types and access levels. For example, patient/Patient.read means "read access to the Patient resource for the authenticated patient." patient/Observation.read means "read access to Observations."

SMART also defines "launch context" — when a patient authenticates, Epic includes their FHIR patient ID in the token response. Your app gets the patient ID without having to ask for it separately.

Epic's FHIR API requires SMART authentication. There's no API key shortcut — every call needs a Bearer token obtained through the OAuth flow.

---

## Slide 10 — Epic Sandbox Overview

Epic's sandbox is a non-production environment available for free to any developer. You register at open.epic.com, no institutional affiliation required. The sandbox comes pre-populated with test patients — Camila Lopez is the most commonly used one. The data is synthetic but realistic.

The sandbox runs a full OAuth 2.0 flow — there's no shortcut to get a token directly. This is actually a good thing for learning, because the real OAuth flow is what you'll implement in production.

One important note: changes to your app registration — like enabling new API capabilities — take a few minutes to provision in the sandbox. This catches people off guard. If you add a new capability and immediately try to use it, you might still get a 403. Wait a few minutes and try again.

---

## Slide 11 — FHIR Resources Used in app2

Let me summarize the four FHIR queries app2 makes and their differences.

Patient is the simplest. You just call GET /Patient with no parameters. Epic uses what's called a "me context" — it infers the patient from the access token itself. No search parameters needed.

MedicationRequest is different. There's no me context. You have to pass the patient's FHIR ID as a search parameter: ?patient=that-ID. Epic includes the patient ID in the token response, so we capture it during the OAuth callback and store it alongside the access token.

Observation also requires the patient parameter. But it has an additional requirement: a category parameter to filter which type of observations you want. category=laboratory gives you lab results; category=vital-signs gives you vitals. We'll go deep on this when we discuss Observation.

---

## SECTION 3 — Application Architecture

---

## Slide 12 — Server-Side Rendering vs SPA

Let me compare SSR with HTMX to the SPA approach, because the choice shapes everything about how the code is structured.

In a single-page application built with React or Vue, the server acts as a data API. It returns JSON. The JavaScript running in the browser receives that JSON, transforms it into HTML, and updates the page. You have two distinct tiers: a Python API backend and a JavaScript frontend. Two runtimes. Two languages. A build pipeline. Two sets of tests.

In an SSR app with HTMX, the server renders complete HTML — both full pages and small fragments for partial updates. There's no JavaScript transformation step. The browser receives finished HTML and displays it. HTMX handles the interactivity by making HTTP requests and swapping the responses into the DOM.

The result: all logic lives in Python. No context switching. No JavaScript build pipeline. One runtime to reason about. For a FHIR application where the data and the auth live entirely on the server, this is a very natural fit.

---

## Slide 13 — The Full Tech Stack

Let's name the components. FastAPI is the web framework, running under uvicorn, which is the ASGI server. HTMX handles UI interactivity — it's a CDN script tag, not a package. Jinja2 is the templating engine. HTTPX is the async HTTP client for making outbound calls to Epic.

Starlette's SessionMiddleware handles session cookies, and it depends on itsdangerous for signing those cookies. Pydantic Settings reads configuration from the .env file with type validation.

Everything runs in a single Python process. No message queues, no microservices, no npm.

---

## Slide 14 — Request Lifecycle

Let me walk through the full lifecycle of a single HTMX request so you can see how all the layers interact.

The user clicks "GET /Patient" in the browser. HTMX intercepts the click and sends a GET request to /fhir/patient, including the session cookie automatically because it's a same-origin request.

On the server, SessionMiddleware intercepts the request first. It reads the session cookie, verifies the HMAC signature using itsdangerous, decodes the JSON payload, and attaches it to the request as request.session. This all happens before the route handler runs.

The router matches /fhir/patient to the fhir_get_patient handler. The handler reads session_id from request.session, then looks up the access token from app.state.token_store — the server-side dict that holds all the tokens.

The handler then calls Epic's FHIR API using the shared httpx.AsyncClient, passing the Bearer token in the Authorization header. The await means the event loop can serve other requests while we're waiting for Epic to respond.

Epic validates the JWT, checks the scope, and returns a FHIR Bundle. The handler pretty-prints the JSON, wraps it in a pre tag, and returns it as an HTMLResponse.

HTMX receives that HTML fragment and injects it into the div with id="result". No navigation. No reload. The address bar doesn't change.

---

## Slide 15 — Why SSR + HTMX for a FHIR App?

There are three specific reasons this architecture fits FHIR applications especially well.

First, access tokens never reach the browser. Epic access tokens are Bearer credentials — whoever holds one can make FHIR calls. By keeping them server-side in the token store and only sending a session_id cookie to the browser, we minimize the attack surface significantly. Even if an attacker could read the session cookie, they'd only get a short random string that's useless without access to the server.

Second, Python is where FHIR logic belongs. Parsing FHIR Bundles, checking scope strings, decoding JWTs, validating token expiry — this is all cleaner in typed Python than it would be in JavaScript. There's no JSON-to-JavaScript-to-HTML pipeline to reason about.

Third, operational simplicity. There's one process to run, one set of logs to read, one deploy artifact. No separate frontend build, no CDN for the SPA. For a learning project or a clinical prototype, that simplicity has real value.

---

## SECTION 4 — Tech Stack Deep Dive

---

## Slide 16 — FastAPI: Async-First Web Framework

FastAPI is built on two things: Starlette, which is an async web toolkit, and Pydantic, which is a data validation library. Together they give you an async web framework with automatic request parsing, type checking, and auto-generated API docs.

The key word is async. FastAPI is designed for I/O-bound workloads — workloads where the application spends most of its time waiting for something else: a database query, an HTTP response, a file read. When you call Epic's FHIR API, you might wait 100 to 500 milliseconds for a response. In a synchronous framework, that wait blocks the entire process. In an async framework, that wait suspends just that one handler and lets the event loop serve other requests.

For an application that makes external HTTP calls on every user action, this matters a great deal in production.

---

## Slide 17 — FastAPI: Async / Await

The code example shows the pattern. Every route handler is declared async def. Inside the handler, when we make the HTTP call to Epic, we use await. That await yields control back to the event loop during the network round-trip.

The rule is simple: async propagates upward. If a function uses await, it must be declared async def. If a function calls an async def function, it must itself be async def. You can't await inside a regular synchronous function — Python will raise a SyntaxError.

The one thing to watch out for is accidentally using synchronous blocking code inside an async handler. The synchronous requests library, time.sleep, or reading a large file with the standard open() function — these block the entire event loop. Use httpx.AsyncClient for HTTP, asyncio.sleep for delays, and asyncio.to_thread() to run blocking functions in a thread pool.

---

## Slide 18 — FastAPI: APIRouter and Application Assembly

main.py in app2 is intentionally thin. Its only job is to create the FastAPI application, register middleware, and mount routers. The actual route handlers live in the routers/ directory.

auth.py handles the OAuth routes: /login, /callback, and /logout. pages.py handles everything else: the home page, the portal page, and all the FHIR HTMX endpoints.

Each router is an instance of APIRouter. You mount them in main.py with include_router. When you pass a prefix, every route in that router gets the prefix prepended. So /login in auth.py becomes /auth/login in the full application.

One decorator parameter worth noting: include_in_schema=False. When set to True — which is the default — a route appears in FastAPI's auto-generated OpenAPI documentation at /docs. HTMX fragment endpoints are internal UI implementation details; they shouldn't appear as public API endpoints. Setting include_in_schema=False keeps /docs clean and signals to future developers that these routes are not a stable external contract.

---

## Slide 19 — FastAPI: The Request Object

The Request object is the integration point for everything that enters a route handler. Understanding what's on Request is the key to reading app2's code.

request.session is the decoded session cookie payload. SessionMiddleware puts it there before your handler runs. It's a dict-like object — you read from it and write to it, and the middleware automatically persists your changes to the cookie on the way out.

request.app is the FastAPI application instance. request.app.state is the State namespace set up during lifespan — that's where token_store and http_client live. request.query_params gives you URL query string parameters — used heavily in the OAuth callback to read the code and state parameters from Epic.

There's a subtle but important point here: route handlers don't import the app object directly. They access it through request.app. This avoids circular imports between the main module and the routers, and it means any router can access application state without any import dependency on any other module.

---

## Slide 20 — FastAPI: Middleware Pipeline

Middleware is code that runs on every request and every response, before and after route handlers. You register it once in main.py and it applies everywhere automatically.

SessionMiddleware is the only middleware in app2. On the inbound path, it reads the session cookie, verifies the itsdangerous HMAC signature, decodes the JSON payload, and attaches the result as request.session. If the cookie is absent or tampered with, request.session is just an empty dict.

On the outbound path, after your handler returns, SessionMiddleware serializes request.session back to JSON, signs it, and sets the Set-Cookie header on the response. This is automatic — any mutation you make to request.session inside a handler is persisted without you having to call any "save" function.

Two configuration options matter: https_only should be True in production — it sets the Secure flag on the cookie, requiring HTTPS. same_site="lax" allows the browser to send the cookie on top-level cross-site GET requests, which is necessary for Epic's redirect back to our callback URL.

---

## Slide 21 — HTMX: The Hypermedia Model

HTMX's philosophy comes from a concept called HATEOAS — Hypermedia as the Engine of Application State. The idea is that HTML, with its links and forms, already describes what a user can do next. HTMX extends this by making any HTML element capable of making HTTP requests and updating the page with the response.

The practical consequence is the most important thing to internalize when working with HTMX: endpoints must return HTML, not JSON. HTMX takes whatever the server returns and injects it directly into the DOM. There's no JavaScript step that reads JSON and builds markup from it.

This is a fundamental shift from API-first thinking. In app2, every FHIR route handler returns either a pre tag with formatted JSON inside it, or a paragraph tag with an error message. The server is not a data provider. The server is an HTML renderer.

---

## Slide 22 — HTMX: Attribute Vocabulary

HTMX is entirely controlled through HTML attributes. There's no JavaScript to write. Let me walk through the five attributes used on every button in app2's portal.

hx-get specifies the HTTP method and the URL to call when the element is activated. hx-target is a CSS selector pointing to the element that will receive the server's response. hx-swap specifies how to insert the response — innerHTML replaces the inner content of the target while keeping the target element itself. hx-indicator points to an element that HTMX will make visible while the request is in flight — our "Loading…" span. And hx-disabled-elt disables the specified element for the duration of the request, preventing double-clicks.

There are many more HTMX attributes worth knowing as you extend the app. hx-trigger lets you fire requests on events other than click — change, keyup with a debounce delay, or even a polling interval. hx-boost upgrades all links and forms in a subtree to HTMX requests automatically. hx-push-url updates the browser's address bar without a navigation.

---

## Slide 23 — HTMX: Error Handling

Here's a behavior of HTMX that surprises many developers: when your server returns a 4xx or 5xx status code, HTMX does not swap the response body into the target. It fires an error event and leaves the page unchanged. This is by design — HTMX assumes error responses are not valid content for the page.

The consequence for app2: FHIR route handlers must return HTTP 200 with a styled error HTML fragment when something goes wrong. Never return HTTPException or a 4xx status from an HTMX endpoint.

app2 uses a _error_html() helper for exactly this. It takes a message string and an optional detail string, and returns an HTMLResponse at 200 with styled error markup. Every error path in every FHIR handler goes through this helper. The error message appears inline in the #result div — in context, no full-page reload, no navigation.

---

## Slide 24 — Jinja2: Server-Side Templating

Jinja2 is the templating engine. Templates are HTML files that live in app2/templates/. They contain placeholders and control structures using Jinja2's syntax: double-braces for variables, percent-brace tags for logic.

The context dict is the only bridge from Python to the template. Everything the template references must be explicitly included in that dict. FastAPI automatically adds request to the context, which is why you can call request.url_for() directly in templates to generate static file URLs.

The best practice is to pass pre-formatted values, not raw Python objects. In app2, id_token_claims_json is already formatted by json.dumps before it's passed to the template. expires_display is already formatted as a readable date string. The template just injects these values — it doesn't compute or format anything.

Autoescaping is Jinja2's built-in XSS defense. It converts angle brackets and quote characters to HTML entities when rendering variables. The | safe filter bypasses this. Use | safe only when the content is server-generated and trusted — never on user-supplied input.

---

## Slide 25 — Jinja2: Template Inheritance

Template inheritance is how portal.html and patient.html relate to each other. portal.html is the base template. It defines the HTML structure, loads HTMX, loads CSS, loads Font Awesome, and declares two named blocks: actions and content. Those blocks are placeholders — they're empty in portal.html.

patient.html extends portal.html. It fills the actions block with the FHIR buttons, and it fills the content block with the #result div. When Jinja2 renders patient.html, it inserts the full portal.html structure and replaces the blocks with patient.html's content.

A few things worth knowing: { super() } lets you include the parent block's content before adding your own — useful for appending rather than replacing. You can have multiple levels of inheritance — a grandchild template can extend a child template, which extends the base. And always use Jinja2 block comments — curly-brace hash — in base templates rather than HTML comments, because Jinja2 evaluates block tags even inside HTML comments and will throw a TemplateSyntaxError.

---

## Slide 26 — HTTPX: Async HTTP Client

httpx is the async HTTP client. It's used for every outbound HTTP call in app2: the back-channel token exchange with Epic, and every FHIR API call.

The reason we use httpx and not requests is async. requests is synchronous — calling requests.get() blocks the thread until the response arrives. In an async FastAPI handler, blocking the thread means blocking the entire event loop. While you're waiting for Epic to respond, no other requests can be processed.

httpx.AsyncClient is the async-native alternative. It has essentially the same API as requests but suspends with await during I/O.

We create one AsyncClient during lifespan and share it across all requests via app.state.http_client. This is important because AsyncClient maintains a pool of persistent TCP connections. Reusing that pool means we pay the TLS handshake cost to Epic once, not on every request.

Always check response.is_success before calling response.json(). Error responses from Epic may return plain text or XML, and calling .json() on a non-JSON body raises a JSONDecodeError.

---

## SECTION 5 — Epic App Registration

---

## Slide 27 — Confidential vs Public Clients

OAuth 2.0 distinguishes between two types of clients. A confidential client is a server-side application that can securely hold a client secret. A public client is a browser-based SPA or mobile app where any secret would be visible to the user.

app2 is a confidential client. The client secret lives in .env on the server. It's sent in the body of the token exchange POST — which happens back-channel, from our server to Epic's token endpoint. The browser never sees the secret.

If you were building a React SPA that talks to Epic directly from the browser, you'd need to use a public client with PKCE — Proof Key for Code Exchange — instead of a client secret. That's a different flow, but the concepts are similar.

---

## Slide 28 — App Registration: Step by Step

Registering the app takes about five minutes. Log into open.epic.com, navigate to My Apps, click Create. Set the Application Audience to Patients. Check the Is Confidential Client box — this is critical. Add your redirect URI — for local development that's http://localhost:8000/auth/callback.

Then select API capabilities individually. Do not select "All FHIR R4 scopes." That option generates a scope string of approximately 5000 characters. When Epic returns all those scopes in the token response and we try to store them in the session cookie, we exceed the browser's 4096-byte cookie size limit. Browsers silently discard oversized cookies. The session disappears with no error.

After submitting, copy the Client ID and the Client Secret immediately. The portal later shows only a hash of the secret — if you navigate away without copying it, you'll need to regenerate it.

Leave the JWK Set URLs blank. Those are for a different authentication method called private_key_jwt. We're using client_secret_post.

---

## Slide 29 — API Capabilities: Observation is Category-Specific

Most FHIR resource types have a single capability toggle in the app registration. Enable Patient.Read and you can read any Patient resource your token's scope allows.

Observation is different. Epic registers Observation access per clinical category. There are separate toggles for Vital Signs, Laboratory, Social History, and others. Each toggle you enable results in a distinct scope entry in the token response.

The scope format uses SMART v2's parameterized notation: patient/Observation.r?category= followed by the full category system URL and the category code, separated by a pipe. It looks verbose, but the important parts are just the code at the end: laboratory or vital-signs.

Epic enforces these grants independently at the API level. If your token includes the laboratory grant but not vital-signs, a request for category=vital-signs returns 403 — even though both queries target the same /Observation resource type. This catches people off guard.

---

## Slide 30 — Sandbox vs Production Scope Behavior

This is one of the most practically important things to understand about the Epic sandbox, because it's genuinely different from how production works.

In the sandbox, the EPIC_SCOPE value in your .env is essentially just a trigger to initiate the OAuth flow. Whatever you put there — even just "openid fhirUser" — Epic grants all of the API capabilities that are registered in your developer portal app registration. The scope string in the authorization request doesn't control what you get.

The practical implication: if you get a 403 on a FHIR call in the sandbox, the fix is in the portal registration, not in EPIC_SCOPE. Go to open.epic.com, enable the missing capability, wait a few minutes, log out of your app, reconnect to Epic, and check the Scope row on the home page. You should see the new category scope appear.

In Epic's production environment, behavior matches the SMART on FHIR spec strictly. You must explicitly request every scope the app needs in the authorization URL. Only the requested and registered scopes are granted. If you deploy app2 to production with EPIC_SCOPE="openid fhirUser", you'll get exactly two scopes and zero clinical data access.

The lesson: EPIC_SCOPE needs no changes during sandbox development, but must be updated before going to production.

---

## SECTION 6 — OAuth 2.0 Authorization Code Flow

---

## Slide 31 — The Authorization Code Flow: Overview

The Authorization Code flow is the standard OAuth 2.0 flow for server-side applications. It's what SMART on FHIR builds on. The defining characteristic is that the access token is obtained through a back-channel server-to-server exchange — the browser never sees it.

There are two categories of steps. Front-channel steps involve browser redirects. The user's browser is the active participant, and the address bar changes at each step. Back-channel steps are server-to-server — our Python code talks directly to Epic's token endpoint, and the browser waits passively.

The sequence is: our app sends the browser to Epic. The user logs in on Epic's page. Epic sends the browser back to us with a short-lived authorization code. Our server immediately exchanges that code for an access token by making a direct POST to Epic's token endpoint. The token comes back to our server, not to the browser. We store it server-side and set a session cookie for the browser.

---

## Slide 32 — Step 1: Building the Authorization URL

The entry point is GET /auth/login. When the user clicks "Connect to Epic Sandbox," the browser hits this route.

The first thing we do is generate a random state value using secrets.token_urlsafe(32). This produces 32 cryptographically random bytes, Base64URL-encoded — about 43 characters. We store it in the session: request.session["oauth_state"] = state.

We then build the authorization URL with several query parameters: response_type=code tells Epic we're doing the Authorization Code flow; client_id identifies our application; scope is our requested scope string; state is the random value we just generated; and redirect_uri tells Epic where to send the browser after the user authenticates.

We URL-encode the parameters using urllib.parse.urlencode. This is important because SMART scope strings contain forward slashes, and Epic requires those to be percent-encoded in the query string.

We respond with a redirect to the Epic authorization URL.

---

## Slide 33 — Step 2: State Parameter and CSRF Protection

Let me explain what the state parameter does and why it matters so much in a healthcare context.

State is a CSRF protection mechanism. Without it, the callback endpoint is vulnerable to what's called a login CSRF attack. Here's how it works: an attacker initiates an OAuth flow against your app but doesn't complete the login. They capture the callback URL that Epic would redirect to — one with a valid authorization code. They then trick a victim into visiting that callback URL. The victim's browser completes the callback, their session is set up, but they're now authenticated as the attacker's identity. In a FHIR context, that's a potential patient record breach.

State prevents this. When the callback arrives, we compare the state value from Epic's redirect against the oauth_state we stored in the session before the flow started. If they don't match — or if there's no oauth_state in the session, meaning the user never initiated a flow from this browser — we return 400 immediately.

We use pop() instead of get() to read the stored state. This makes the state single-use: once it's been validated, it's removed from the session. The same callback URL can't be replayed.

---

## Slide 34 — Step 3: Back-Channel Token Exchange

After state validation passes, we have a valid authorization code. We immediately POST it to Epic's token endpoint. This is the back-channel exchange — it happens entirely on our server, using the shared httpx.AsyncClient.

The POST body is form-encoded and includes grant_type set to authorization_code, the code itself, the redirect_uri (Epic validates that it matches the registration), our client_id, and our client_secret.

The authorization code expires in about 60 seconds, so we exchange it immediately — no waiting.

Epic responds with a JSON payload containing the access_token, token_type (always "Bearer"), expires_in in seconds, scope, and — when the openid scope is granted — an id_token. For patient-scoped launches, Epic also includes a patient field containing the FHIR ID of the in-context patient.

We wrap the httpx call in try/except httpx.TransportError to catch network-level failures. Without this, a connection reset or timeout propagates as an unhandled 500.

---

## Slide 35 — Step 4: Session Storage After Token Exchange

After the token exchange succeeds, we store the data in two places.

The token store — app.state.token_store — gets the full token payload, keyed by a randomly generated session_id. It stores five things: access_token, refresh_token, scope, id_token (for the identity dialog), and patient (for FHIR queries that need it).

The session cookie gets only lightweight metadata: the session_id to link back to the token store, token_expires_at as an ISO 8601 string, and scope for display on the home page. Three short values, well within the 4096-byte cookie limit.

The reason for this separation is the cookie size limit. An Epic JWT access token alone is about 880 characters. Add a refresh token, scope string, and serialization overhead, and you're over 4096 bytes. Browsers silently discard oversized cookies — the session just disappears. By keeping tokens server-side and only putting a pointer in the cookie, we completely avoid this issue.

---

## Slide 36 — The Meta-Refresh Trick

After storing the session, we need to send the browser to the home page. You might expect a simple 302 redirect. But 302 breaks the session cookie in Chrome and Safari.

Here's why: the callback URL is reached by following a redirect from Epic's domain. This makes it part of a "cross-site redirect chain." When a browser receives a response from our domain at the end of that chain, Chrome and Safari treat it as a cross-site context and refuse to store SameSite=Lax cookies set on redirect responses. The cookie is set, but it never reaches the browser's cookie store.

The fix is to return a 200 response with a meta-refresh tag in the HTML head. The meta-refresh tells the browser to navigate to / after one second. But because we returned 200 instead of 302, the browser has already "landed" on our origin. The Set-Cookie header is processed normally. Then when the navigation to / fires, the cookie is already stored, and that request carries it.

This is a subtle browser behavior that took some investigation to discover. The app2-guide.md has a full explanation if you want to understand the spec details.

---

## SECTION 7 — JWTs and Token Management

---

## Slide 37 — What is a JWT?

JWT stands for JSON Web Token, pronounced "jot." It's a compact string that carries signed claims — assertions about a subject, like "this token was issued by Epic, expires at timestamp X, and grants scope Y."

A JWT has three segments separated by dots. Each segment is Base64URL-encoded. The first is the header, which identifies the signing algorithm. The second is the payload, which is the actual JSON claims data. The third is the signature, which proves the token was created by the holder of a specific private key.

All three segments start with "eyJ" when you look at them as strings, because that's what Base64URL-encoding of the opening brace of a JSON object produces.

A critical property: the payload is not encrypted. Anyone can decode it and read the claims. The signature only proves authenticity and integrity — it doesn't hide the content. This is important for our ID Token dialog, where we decode and display the claims without needing a key.

---

## Slide 38 — JWT Payload: Key Claims

Let me describe the most important claims you'll see in an Epic access token payload.

iss is the issuer — Epic's OAuth base URL. sub is the subject — the authenticated user's Epic internal ID. aud is the audience — who the token is intended for, which is Epic's FHIR base URL. client_id identifies your registered application. iat and exp are issued-at and expiration as Unix timestamps — Epic typically issues one-hour tokens. jti is a unique identifier for this specific token instance.

scope is the granted scope string — space-separated, with Epic's abbreviated notation. fhirUser is the full FHIR URL of the authenticated user's Patient or Practitioner resource. And patient is the short-form FHIR ID of the in-context patient — this is what we store and use as a search parameter for MedicationRequest and Observation queries.

---

## Slide 39 — Access Token vs ID Token

When the openid scope is granted, Epic returns two JWTs. They have very different purposes and different intended readers.

The access_token is a Bearer credential for the FHIR API. Its intended reader is the resource server — Epic's FHIR endpoints. When your app makes a FHIR call, you put the access_token in the Authorization header. The FHIR server validates its signature, checks the expiry, and confirms the granted scopes. Your app should treat the access_token as opaque — forward it unchanged, don't decode it, don't build application logic based on its claims.

The id_token is an OIDC identity assertion. Its intended reader is your application. It contains claims about who authenticated: their Epic user ID, their fhirUser URL, optionally their name. app2 decodes the id_token to display these claims in the ID Token dialog. We never send the id_token to the FHIR API.

app2 stores both tokens in the server-side token store.

---

## Slide 40 — The Server-Side Token Store

Let me explain the token store in detail because it's a core architectural decision.

app.state.token_store is a simple Python dict. It's created empty during lifespan startup and lives for the lifetime of the server process. Keys are session_ids — random hex strings generated at login. Values are dicts containing the five token fields we discussed: access_token, refresh_token, scope, id_token, and patient.

Why not store the tokens in the session cookie? An Epic JWT is about 880 characters. Once you add the refresh token, scope string, and the overhead of JSON serialization and Base64-URL signing by itsdangerous, you easily exceed the browser's 4096-byte cookie limit. Browsers silently discard the oversized cookie — the session just vanishes.

By storing only a short session_id in the cookie, we keep the cookie well under the limit regardless of how long the scope string or tokens are.

The limitation is that this store is in-memory. If the server restarts, it's cleared. Users who had active sessions will need to log in again. For a learning application this is fine. For production, you'd replace this dict with Redis, which survives restarts and works across multiple server processes.

---

## Slide 41 — The ID Token Dialog

The ID Token dialog is a good example of how the pieces fit together. Let me trace the full flow.

During /auth/callback, we receive the id_token from Epic and store it in token_store alongside the access_token.

On every request to the home page GET /, the handler retrieves the raw id_token from the token store. It calls _decode_jwt_payload(), which splits the JWT on dots, takes the middle segment (the payload), adds Base64 padding characters that Base64URL omits, and decodes it to a Python dict. Then it calls json.dumps with indent=2 to produce a pre-formatted JSON string, and passes that string to the Jinja2 template as id_token_claims_json.

In the template, we conditionally render both an "ID Token" button and a dialog element only when id_token_claims is not None. The button calls showModal() on the dialog. The dialog element is a native HTML5 element — no library needed. It provides built-in focus trapping, ESC-to-close, and a backdrop overlay. We add backdrop-click-to-close with a three-line inline onclick.

The | safe filter on the JSON output is intentional — we bypass Jinja2's autoescaping because this content is server-generated JSON, not user input. Without | safe, the double-quote characters in the JSON become &quot; and the output is unreadable.

---

## SECTION 8 — FHIR API Calls

---

## Slide 42 — The Six-Step Handler Pattern

Every FHIR route handler in pages.py follows the same six-step structure. Once you understand one handler, you understand all of them.

Step 1: read session_id from request.session. If there's no session_id, the user isn't logged in. Return an error fragment immediately.

Step 2: look up the access_token from app.state.token_store using the session_id. If the entry is missing — usually because the server restarted and the in-memory store was cleared — return an error fragment with instructions to reconnect.

Step 3: check token expiry. Read token_expires_at from the session cookie, parse it as an ISO 8601 datetime, compare it to now. If the token has expired, return an error fragment. This avoids sending a request that Epic will reject with a 401.

Step 4: call Epic's FHIR API using the shared AsyncClient, passing the Bearer token in the Authorization header and application/fhir+json in the Accept header. Wrap in try/except httpx.TransportError.

Step 5: check response.is_success. If it's False, return an error fragment with the HTTP status code and the raw response body.

Step 6: json.dumps the response JSON with indent=2, wrap it in a pre tag, return an HTMLResponse.

---

## Slide 43 — GET /Patient: The Me Context

The Patient handler is the simplest of the four FHIR calls. It follows all six steps, but step 2 only needs the access_token — no patient ID lookup.

That's because Epic implements what's called a "me context" for the Patient resource. When you call GET /Patient with a valid access token from a patient-scoped session, Epic automatically returns the patient associated with that token. You don't pass a search parameter.

This is a SMART on FHIR convention. The FHIR server infers the patient from the patient claim in the JWT access token payload. You don't need to decode the token to use this — Epic does it on their end.

The response is a FHIR Bundle with a single Patient entry, or sometimes the Patient resource directly. Either way, we pretty-print it and return it as an HTML fragment.

---

## Slide 44 — GET /MedicationRequest: Patient-Scoped Search

MedicationRequest doesn't have a me context. Epic requires you to specify which patient's medication requests you want. Without the patient parameter, Epic returns an error.

Where do we get the patient ID? It comes from Epic's token response. During the back-channel token exchange in /auth/callback, Epic includes a "patient" field in the JSON response for patient-scoped launches. That's the FHIR ID of the in-context patient — the one who just authenticated. We store it in token_store["patient"] during callback processing.

In the handler, step 2 now retrieves both access_token and patient from the token_store. If patient is empty, we return an error fragment explaining that a patient-scoped launch is required. If it's present, we pass it as params={"patient": patient_id} to the httpx get call. httpx serializes that dict to the query string automatically.

The response is a FHIR Bundle where each entry is a MedicationRequest resource representing one prescription.

---

## Slide 45 — The Observation Resource

Observation is FHIR's most versatile resource type. It's a catch-all for clinical measurements and findings. Lab results, vital signs, SDOH questionnaire responses, smoking status, body measurements — they all come back as Observation resources.

What makes them consistent is the structure. Every Observation has a code element that identifies what was measured, usually a LOINC code. The value[x] element holds the result — it can be a Quantity with a unit, a coded value, a string, or a boolean. There's a subject referencing the patient, an effectiveDateTime, and a category element that identifies the clinical domain.

Filtering by category is essential. Without it, a single search returns everything mixed together — a potentially huge Bundle with labs, vitals, and surveys all interleaved. category is what lets you say "give me just the lab results" or "give me just the vital signs."

---

## Slide 46 — Observation: The Category System

The category system URI is http://terminology.hl7.org/CodeSystem/observation-category. In the URL query string, you pass just the code — not the full system URL. Epic looks up the system automatically.

The three categories that matter for app2 are laboratory for lab results, vital-signs for vital sign measurements, and survey for questionnaire responses. Note that vital-signs uses a hyphen, is lowercase, and must be spelled exactly right — it's a case-sensitive FHIR code value.

For the lab reports endpoint, the query becomes GET /Observation?patient=<id>&category=laboratory. For vital signs, it's GET /Observation?patient=<id>&category=vital-signs. The only difference between the two handlers is this category value.

---

## Slide 47 — GET /Observation: Lab Reports + Vital Signs

Both Observation handlers follow the same six-step pattern as MedicationRequest. Step 2 retrieves both access_token and patient — both are required. The handlers differ only in the category parameter passed in step 4.

An important behavior to know: an empty bundle is a valid 200 response. If the sandbox test patient has no recorded lab results, Epic returns a Bundle with total: 0 and an empty entry array. The handler formats and returns this normally. You'll see the Bundle structure in the pre tag with no entries. This is correct, not an error.

For both endpoints to work, you need the corresponding capability enabled in the Epic developer portal: Observation.Read — Laboratory for labs, and Observation.Read — Vital Signs for vitals. And remember — Epic enforces these grants independently. Having the laboratory grant doesn't give you vital signs access even though it's the same resource type.

---

## Slide 48 — Observation: Result Volume and Pagination

This is something to be aware of before deploying against real patients.

In the sandbox, the test patient has limited clinical history. Lab and vital sign requests return small bundles — manageable to display. In a real clinical system, a patient with years of history might have hundreds or even thousands of Observation entries.

Epic supports pagination through the FHIR Bundle.link mechanism. When you add a _count parameter to your query, Epic limits the result set to that many entries. When more results exist, the response Bundle includes a link array with a next relation pointing to the URL for the next page.

app2 doesn't implement _count or pagination yet. For sandbox development, it's not needed. When you extend the app for real patient data, you'll want to add _count=20 or similar to the params dict, and implement logic to detect and follow the next link.

---

## SECTION 9 — Key Design Patterns

---

## Slide 49 — Lifespan and app.state

FastAPI's lifespan context manager is the correct place to create and destroy application-level resources. It runs once at startup, before the first request, and once at shutdown.

app2's lifespan creates three resources. The shared httpx.AsyncClient — one client for the entire application, maintaining a TCP connection pool to Epic. The Jinja2Templates instance — pre-loads the template directory, resolving the path relative to main.py using Path(__file__).parent for robustness. And the token_store dict — starts empty, accumulates entries as users log in.

The shutdown phase calls .aclose() on the AsyncClient. This drains any in-flight requests and closes the pooled TCP connections cleanly.

Why not use module-level globals instead? Three reasons: AsyncClient must be created inside a running event loop, which doesn't exist at module import time. Lifespan guarantees cleanup even if the server exits due to an exception. And app.state is explicit — route handlers access it through request.app.state, making the dependency visible at the call site rather than hidden in a global variable.

---

## Slide 50 — Token Security: Defense in Depth

Let me summarize the security design decisions around token handling.

The back-channel exchange means the access token is retrieved server-to-server. The browser never sees the token in transit. It's not in a redirect URL, not in a query string, not in a form body that the browser submits.

The server-side token store means the token never reaches the browser's storage. The cookie contains only a random session ID — useless on its own. Even if an attacker steals the cookie, they get nothing actionable.

The session cookie is signed by itsdangerous but not encrypted. The payload is base64-encoded JSON — readable by anyone who has the cookie value. We only put non-sensitive metadata in it: session_id, expiry timestamp, scope string. No tokens, no patient identifiers, no PII.

And we forward the access_token to Epic opaquely — we never decode it, never log it, never derive business logic from its internal claims.

---

## Slide 51 — Production Readiness Checklist

When you're ready to move from sandbox to production, here's what needs to change.

Set https_only=True in SessionMiddleware. This adds the Secure flag to the session cookie, preventing it from being transmitted over non-HTTPS connections. This requires HTTPS termination, usually via an nginx reverse proxy.

Replace app.state.token_store with Redis. The in-memory dict is cleared every time the server restarts, requiring users to re-authenticate. Redis persists data across restarts and works correctly with multiple server processes.

Update EPIC_SCOPE to enumerate all required resource scopes. The sandbox grants everything; production doesn't.

Add timeouts to the AsyncClient: Timeout(connect=5.0, read=30.0) prevents hung Epic endpoints from holding handlers open indefinitely.

Run uvicorn behind a process manager like systemd or supervisor instead of --reload. The reload flag is for development only.

Update APP_REDIRECT_URI to the production HTTPS callback URL and register it in your production app registration on Epic.

---

## SECTION 10 — Building Your Own

---

## Slide 52 — Getting Started: The Critical Path

Here's the minimum path to get from zero to a working app.

Set up a Python 3.12 environment and install the dependencies. Register a confidential client at open.epic.com and enable exactly the API capabilities you need. Create .env with your client credentials and a strong SESSION_SECRET_KEY.

Create __init__.py in your app directory — this is required for Python to treat it as a package, which is necessary for the dot-notation uvicorn invocation from the project root. Without it, uvicorn app2.main:app fails with a ModuleNotFoundError.

Build main.py first — just the FastAPI application, lifespan, middleware, and include_router calls. Then auth.py with the three OAuth routes. Then pages.py starting with the home route and the patient portal page.

Run uvicorn from the project root — always from the root. The app2/templates/ path resolution, the .env lookup, and the Python package structure all depend on running from the root directory.

---

## Slide 53 — Diagnosing Common Errors

Let me walk through the errors you're most likely to encounter and how to diagnose them.

403 on a FHIR call: check the Scope row on the home page. If the required scope isn't there, the capability isn't registered or hasn't been provisioned yet. Go to open.epic.com, check the capability is enabled, wait a few minutes, log out, reconnect, check again.

Session disappears after OAuth callback: this is the SameSite cookie issue. Make sure the callback handler returns 200 with meta-refresh rather than 302.

400 State mismatch: the session cookie isn't persisting between /auth/login and /auth/callback. Check that SESSION_SECRET_KEY is set, long enough, and consistent — not regenerated on every request.

Token store empty after clicking a FHIR button: the server restarted and cleared the in-memory store. Log out and reconnect. This is expected behavior with the current architecture.

ReadError on a FHIR call: stale pooled TCP connection — Epic closed the idle connection server-side. Retry once; it usually succeeds immediately.

---

## Slide 54 — Extending the App: What's Next

There are several natural next steps from here.

The most immediate is adding _count pagination for the Observation endpoints. Add "_count": 20 to the params dict and handle the Bundle.link next relation in the response.

You'll notice that fhir_get_lab_report and fhir_get_vital_signs are nearly identical except for the category value. A natural refactor is to extract a _fhir_get_observation(request, category) helper and have both thin route handlers call it. This was intentionally deferred to keep the implementation legible while learning.

For additional FHIR resources: Condition with category=problem-list-item for diagnoses, AllergyIntolerance for allergies, Encounter for visit history, Immunization for vaccination records. All follow the same six-step pattern with slight variations in query parameters.

For production infrastructure: Redis for the token store, nginx for HTTPS termination, systemd for process management, and Oracle Cloud Infrastructure for deployment — the repository's target hosting platform.

---

## SECTION 11 — Key Resources

---

## Slide 55 — Reference Links

Here are the essential references for continuing your work with FHIR and SMART on FHIR.

The SMART on FHIR specification at smart.hl7.org is the authoritative source for the OAuth flow, scope conventions, and launch context. The FHIR R4 specification at hl7.org/fhir/R4 documents every resource type, every search parameter, and every interaction.

Epic's developer portal at open.epic.com has documentation for their specific FHIR API implementation, including which LOINC codes they support for specific observations and which search parameters they allow.

The FastAPI, HTMX, and HTTPX documentation pages are all excellent — well-organized, with good examples.

And the companion developer guide at docs/app2-guide.md in this repository documents every implementation step, every design decision, and every concept we've covered today in full detail. If something in this presentation went too fast, that guide has the depth.

---

## Slide 56 — Closing

Thank you for following along. The complete source code is in the repository. The companion guide at docs/app2-guide.md has everything documented in depth. If you have questions — about the code, about FHIR, about any of the design decisions — now is the time.

---

*End of presenter script.*
