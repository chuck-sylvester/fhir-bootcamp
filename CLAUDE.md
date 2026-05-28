# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Purpose

Companion repository for the Medblocks 10-week FHIR bootcamp. Builds five FHIR applications using Python/SSR as an alternative to the bootcamp's Vite/Svelte stack, with deployment to Oracle Cloud Infrastructure (OCI).

## Claude's Role

- **Documentation collaborator**: Help create and update the per-app developer guides in `docs/`. The owner writes all application code himself to reinforce learning — do not generate application code unless explicitly asked.
- Assist with planning, feedback, and explaining concepts.

## Tech Stack

| Layer | Technology |
|---|---|
| Web framework | FastAPI |
| Frontend | HTMX + Jinja2 Templates (SSR) |
| Database | PostgreSQL (latest stable, via Docker) |
| Auth | Keycloak (local Docker, OAuth2 + OIDC / SMART on FHIR) |
| FHIR server | HAPI FHIR (local Docker) |
| Language | Python 3.12 (target; local env currently on 3.11 — upgrade is an app1 setup task) |
| Shell | zsh (macOS terminal) |
| Local services | Docker (PostgreSQL, Keycloak, HAPI FHIR) |
| Hosting | Oracle Cloud Infrastructure (OCI) — VM-based lift-and-shift |

## Repository Structure

Each application lives in its own top-level folder (`app1/`, `app2/`, etc.), built independently from scratch. Each app folder contains a `cli/` subdirectory for terminal-based experiments and standalone CLI scripts.

Three files are shared at the project root across all apps: `.venv/` (Python environment), `requirements.txt` (dependencies), and `.env` (environment variables). Each app owns its own `config.py`, which reads from the root-level `.env` via `python-dotenv`.

```
fhir-bootcamp/
├── .venv/              # shared Python virtual environment
├── requirements.txt    # shared dependencies
├── .env                # shared environment variables across all apps (not committed)
├── app1/
│   ├── main.py         # FastAPI application entry point
│   ├── config.py       # app1-specific configuration
│   ├── cli/            # CLI scripts and terminal experiments for app1
│   └── ...             # routers/, templates/, static/, etc.
├── app2/
│   ├── config.py
│   └── cli/
├── ...
└── docs/               # one markdown developer guide per app
```

## Development Setup

```bash
python3.12 -m venv .venv
source .venv/bin/activate

# Install shared dependencies
pip install -r requirements.txt

# Run a FastAPI app (always from the project root, using dot notation)
# Always include --port explicitly; default is 8000, but each app may use its own port (app1=8001, app2=8002, etc.)
uvicorn app1.main:app --reload --port 8001

# Run a CLI script (from the project root)
python app1/cli/script_name.py
```

Each app's full run instructions are documented in `docs/appN.md`.

## Local Docker Services

Three backing services run locally via Docker:

| Service | Purpose |
|---|---|
| PostgreSQL | Application database |
| Keycloak | Local AuthN/AuthZ (OAuth2 + OIDC, SMART on FHIR) |
| HAPI FHIR | Local FHIR server (R4) |

Docker Compose will likely manage these together. Each service's setup (image version, ports, env vars, startup order) should be documented in the relevant `docs/appN.md` when first introduced.

## OCI Deployment

Lift-and-shift to one or two OCI VM instances, mirroring the local Docker-based setup. The same Docker services (PostgreSQL, Keycloak, HAPI FHIR) are expected to run on the VM(s) alongside the FastAPI application.

## Documentation Convention

Guides in `docs/appN.md` should be **very detailed**, capturing every essential step and consideration so that a future developer (or the owner's future self) can reproduce the environment and application from scratch. Do not skip steps that seem obvious.

Each guide should cover:
1. Local macOS environment setup (including Python 3.12 upgrade via pyenv, for app1)
2. Creating `__init__.py` in the `appN/` folder (required for dot-notation uvicorn invocation from project root)
3. Tech stack and dependencies used (with version numbers where relevant)
4. Docker service setup: which services the app requires, image versions, port mappings, env vars, startup order
5. How to run the FastAPI app from the project root: `uvicorn appN.main:app --reload`
6. How to run CLI scripts: `python appN/cli/script_name.py`
7. Deployment steps to OCI (mirroring local Docker setup, noting what changes)
