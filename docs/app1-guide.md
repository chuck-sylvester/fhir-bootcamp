# App1: Patient Management Application

## Overview

App1 is a Patient Management Application that interfaces with a HAPI FHIR server using FHIR REST APIs. It is the first of five applications built as part of the Medblocks 10-week FHIR Bootcamp, implemented using a Python SSR stack (FastAPI + HTMX + Jinja2) as an alternative to the bootcamp's Vite/Svelte approach.

## Functional Requirements

1. **List patients** - Display all patients on the FHIR server, showing name, gender, and date of birth.
2. **Create patient** - Submit a form with name, gender, date of birth, and phone number.
3. **Update patient** - Open any existing patient in the same form and save changes back to the FHIR server.
4. **Search by name** - Search patients by name with partial-match support.
5. **Validate data** - All form fields must be validated.
6. *(Bonus)* **Search by name or phone** - Extend search to support partial matching on phone number as well.

## Tech Stack

| Layer         | Technology                               |
|---------------|------------------------------------------|
| Web framework | FastAPI                                  |
| Frontend      | HTMX + Jinja2 Templates (SSR)            |
| HTTP client   | requests (sync, for FHIR REST API calls) |
| Form handling | python-multipart                         |
| FHIR server   | HAPI FHIR (Docker)                       |
| Language      | Python 3.12                              |
| Shell         | zsh (macOS terminal)                     |

---

## Part 1: Environment Setup

### 1.1 Verify Python 3.12 Installation

Python 3.12 was installed alongside the existing 3.11 installation using Homebrew:

```zsh
brew install python@3.12
```

Verify both versions are available:

```zsh
python3.11 --version
python3.12 --version
```

Determine where Homebrew installed Python 3.12:

```zsh
which python3.12
```

On Apple Silicon Macs this is typically `/opt/homebrew/bin/python3.12`. On Intel Macs it is typically `/usr/local/bin/python3.12`.

> **Note:** Do not rely on the unversioned `python3` command — it may still point to 3.11 depending on your PATH. Always invoke `python3.12` explicitly when creating the virtual environment.

### 1.2 Create the Root-Level Virtual Environment

The virtual environment is created once at the project root and shared across all five applications.

Navigate to the project root:

```zsh
cd ~/swdev/cps/fhir-bootcamp
```

Create the virtual environment, explicitly targeting Python 3.12:

```zsh
python3.12 -m venv .venv
```

Verify the correct Python version is used inside the environment:

```zsh
.venv/bin/python --version
```

Expected output: `Python 3.12.x`

### 1.3 Activate the Virtual Environment

```zsh
source .venv/bin/activate
```

After activation, your prompt will be prefixed with `(.venv)`. Confirm the active Python:

```zsh
python --version
which python
```

Both should confirm Python 3.12 inside `.venv`.

> **Reminder:** Activate the virtual environment at the start of every development session before running any application or installing packages.

---

## Part 2: Project Structure

### 2.1 Create the app1 Directory and Required Files

From the project root:

```zsh
mkdir -p app1/cli
```

Create the `__init__.py` file in `app1/`. This file is required so that Python treats `app1` as a package, which enables uvicorn to be invoked using dot notation from the project root:

```zsh
touch app1/__init__.py
```

> **Why this matters:** Without `__init__.py`, the command `uvicorn app1.main:app` will fail with a module resolution error. The file can remain empty.

Create the initial FastAPI entry point:

```zsh
touch app1/main.py
```

Create directories for templates and static files:

```zsh
mkdir -p app1/templates
mkdir -p app1/static
```

The resulting structure for app1:

```
fhir-bootcamp/
├── .venv/
├── .env
├── requirements.txt
├── app1/
│   ├── __init__.py        ← required for dot-notation module resolution
│   ├── main.py            ← FastAPI application entry point
│   ├── config.py          ← app1-specific configuration
│   ├── cli/               ← standalone CLI scripts and experiments
│   ├── templates/         ← Jinja2 HTML templates
│   └── static/            ← CSS, JS, and other static assets
└── docs/
    └── app1.md
```

### 2.2 Create the Configuration Files

#### .env

The `.env` file lives at the project root and is shared across all applications. It holds environment-specific values (server URLs, ports, credentials) that may be needed by more than one app. This file is not committed to version control (it is listed in `.gitignore`). Each app's own `config.py` reads from this single root-level `.env` using `python-dotenv`.

```zsh
touch .env
```

Initial contents for `.env`:

```
FHIR_BASE_URL=http://localhost:8080/fhir
APP1_PORT=8001
```

Note: try to get into the good habit of also creating a `.env.example` file. You (and others) will thank you later.

#### config.py

Create `config.py` inside the `app1/` folder. Each application maintains its own `config.py` to keep configuration self-contained:

```zsh
touch app1/config.py
```

Initial contents for `app1/config.py`:

```python
from dotenv import load_dotenv
import os

load_dotenv()

FHIR_BASE_URL = os.getenv("FHIR_BASE_URL", "http://localhost:8080/fhir")
APP1_PORT = int(os.getenv("APP1_PORT", 8001))
```

---

## Part 3: Dependencies

### 3.1 Install Required Packages

With the virtual environment active, install the app1 dependencies:

```zsh
pip install fastapi "uvicorn[standard]" jinja2 python-multipart requests python-dotenv
```

| Package | Purpose |
|---|---|
| `fastapi` | Web framework |
| `uvicorn[standard]` | ASGI server for running FastAPI (includes websocket and HTTP/2 support) |
| `jinja2` | HTML templating engine |
| `python-multipart` | Required by FastAPI to parse HTML form submissions |
| `requests` | Synchronous HTTP client used to call the HAPI FHIR REST API |
| `python-dotenv` | Loads environment variables from the `.env` file |

> **HTTP client note — `requests` vs `httpx`:** App1 uses the `requests` library, which is synchronous. FastAPI is an async framework, so using `requests` inside an `async def` route handler would block the event loop — preventing the server from handling any other requests while the FHIR call is in progress. The correct pattern is to declare route handlers that call `requests` as plain `def` (not `async def`). FastAPI automatically runs synchronous route handlers in a thread pool, which is the safe and correct behavior.
>
> ```python
> # Correct — FastAPI runs sync route handlers in a thread pool
> @app.get("/patients")
> def list_patients():
>     response = requests.get(f"{FHIR_BASE_URL}/Patient")
>     ...
>
> # Anti-pattern — blocks the FastAPI event loop
> @app.get("/patients")
> async def list_patients():
>     response = requests.get(f"{FHIR_BASE_URL}/Patient")
>     ...
> ```
>
> In a later app, `requests` will be replaced with `httpx`, which natively supports `async/await` and is the idiomatic choice for async FastAPI applications. The `httpx` API is intentionally similar to `requests`, so the transition will be straightforward.

### 3.2 Save Dependencies to requirements.txt

```zsh
pip freeze > requirements.txt
```

This captures exact versions for reproducibility. Any developer setting up the project fresh can run:

```zsh
pip install -r requirements.txt
```

---

## Part 4: HAPI FHIR Server (Docker)

### 4.1 Prerequisites

Docker Desktop must be installed and running on macOS before proceeding. Verify:

```zsh
docker --version
docker info
```

### 4.2 Pull and Run the HAPI FHIR Server

Pull the official HAPI FHIR image:

```zsh
docker pull hapiproject/hapi:latest
```

Run the HAPI FHIR server container:

```zsh
docker run -d \
  --name hapi-fhir \
  -p 8080:8080 \
  hapiproject/hapi:latest
```

| Parameter | Value | Notes |
|---|---|---|
| `--name` | `hapi-fhir` | Container name for easy reference |
| `-p 8080:8080` | host:container | HAPI FHIR listens on port 8080 by default |
| `-d` | — | Runs in detached (background) mode |

### 4.3 Verify the HAPI FHIR Server is Running

Check container status:

```zsh
docker ps
```

The HAPI FHIR server takes approximately 30–60 seconds to fully start. Monitor startup logs:

```zsh
docker logs -f hapi-fhir
```

Wait until you see a line indicating the server is ready (typically `Started Application in X seconds`). Press `Ctrl+C` to stop following the logs.

Once running, the FHIR base URL is: `http://localhost:8080/fhir`

Verify the server is responding by opening the following URL in a browser or running:

```zsh
curl http://localhost:8080/fhir/metadata
```

A successful response returns a FHIR `CapabilityStatement` resource in JSON format.

### 4.4 Managing the HAPI FHIR Container

```zsh
# Stop the container
docker stop hapi-fhir

# Start the container again (data persists within the container)
docker start hapi-fhir

# Remove the container entirely (all data is lost)
docker rm -f hapi-fhir
```

> **Note:** By default, HAPI FHIR stores data in an in-memory H2 database inside the container. Data is preserved as long as the container is not removed. For persistent storage across container removals, a PostgreSQL backend would need to be configured (deferred for a later app).

---

## Part 5: Running the Application

### 5.1 Run the FastAPI Application

Always run from the **project root** with the virtual environment active:

```zsh
source .venv/bin/activate
uvicorn app1.main:app --reload --port 8001
```

| Parameter | Purpose |
|---|---|
| `app1.main:app` | Dot-notation module path: `app1/main.py`, `app` object |
| `--reload` | Auto-restarts the server on code changes (development only) |
| `--port 8001` | Explicit port assignment for app1 |

The application will be available at: `http://localhost:8001`

### 5.2 Run CLI Scripts

CLI scripts live in `app1/cli/` and are run from the project root with the virtual environment active:

```zsh
python app1/cli/script_name.py
```

---

## Part 6: FHIR Patient Resource Reference

The FHIR `Patient` resource fields used by this application:

| FHIR Field | Path | Notes |
|---|---|---|
| Name | `name[0].family`, `name[0].given[0]` | HumanName type; family + given |
| Gender | `gender` | Values: `male`, `female`, `other`, `unknown` |
| Date of birth | `birthDate` | Format: `YYYY-MM-DD` |
| Phone number | `telecom[].value` where `system = "phone"` | ContactPoint type |

Key FHIR REST API endpoints used:

| Operation | Method | Endpoint |
|---|---|---|
| List all patients | GET | `/fhir/Patient` |
| Search by name | GET | `/fhir/Patient?name=<value>` |
| Search by phone | GET | `/fhir/Patient?phone=<value>` |
| Get one patient | GET | `/fhir/Patient/<id>` |
| Create patient | POST | `/fhir/Patient` |
| Update patient | PUT | `/fhir/Patient/<id>` |
| Delete patient | DELETE | `/fhir/Patient/<id>` |

---

## Change Log

| Date | Description |
|---|---|
| 2026-05-28 | Initial document created — environment setup, project structure, dependencies, HAPI FHIR Docker setup, FHIR Patient reference |
| 2026-05-28 | Swapped `httpx` for `requests` as the HTTP client; added `def` vs `async def` route handler guidance |
| 2026-05-28 | Moved `config.py` from project root into `app1/`; each app owns its own configuration |

