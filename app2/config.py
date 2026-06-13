# -----------------------------------------------------------------
# fhir-bootcamp/app2/config.py
# -----------------------------------------------------------------
# FastAPI application configuration using Pydantic
# -----------------------------------------------------------------

from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings (BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Application
    app_name: str = "FHIR Bootcamp (Python)"
    app_description: str = "app description"
    app_version: str = "0.0.0.0"
    app_env: str = "development"

    # Logging
    log_level: str = "INFO"

    # Debug Settings
    app_debug: bool = True

    # Session
    session_secret_key: str

    # OAuth 2.0 Info
    epic_nonprod_client_id: str
    epic_client_secret: str
    epic_authorize_url: str
    epic_token_url: str
    epic_fhir_base_url: str = "https://fhir.epic.com"
    epic_scope: str
    app_redirect_uri: str

# Module-level singleton - instantiated once when module is first imported
settings = Settings()
