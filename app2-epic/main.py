# ---------------------------------------------------------------------
# fhir-bootcamp/app2/main.py
# ---------------------------------------------------------------------
# Application entry point: creates FastAPI app
# Run from project root via:
#   uvicorn app2.main:app --reload --port 8000
# ---------------------------------------------------------------------

from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from app2.config import settings
from app2.routers import auth, pages

# Create FastAPI lifespan context manager
@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.http_client = httpx.AsyncClient()
    app.state.templates = Jinja2Templates(directory=Path(__file__).parent / "templates")
    app.state.token_store = {}  # inline memory token store keyed by session_id
    yield
    # Gracefully close HTTP client on shutdown to release connections
    await app.state.http_client.aclose()

# Create FastAPI app instance
print("===> creating FastAPI app...")
app = FastAPI(
    title=settings.app_name,
    description=settings.app_description,
    version=settings.app_version,
    debug=settings.app_debug,
    lifespan=lifespan
)

# Set up session middleware
print("===> setting up middleware...")
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.session_secret_key,
    https_only=False,  # set True in production to require https
    same_site="lax"
)

# Mount static directory
app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")

# Register routers
print("===> registering routes...")
app.include_router(auth.router, prefix="/auth", tags=["Auth"])
app.include_router(pages.router, tags=["Pages"])


# System routes
@app.get("/health", tags=["System"])
async def health_check():
    return {
        "app_name": settings.app_name,
        "app_version": settings.app_version,
        "app_environment": settings.app_env,
        "system_status": "healthy"
    }