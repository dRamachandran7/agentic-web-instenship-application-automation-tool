"""Runtime configuration for the frontend orchestrator.

Values are read from environment variables (a local `.env` file is loaded
automatically). Defaults match the ports each service's own README tells you
to run it on.
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="", extra="ignore")

    search_listings_url: str = "http://localhost:8001"
    analyze_listing_url: str = "http://localhost:8002"
    personalize_resume_url: str = "http://localhost:8003"
    submit_application_url: str = "http://localhost:8004"

    # Timeout for each service call. Generous because personalize_resume
    # includes an LLM call plus a LaTeX compile.
    request_timeout_s: float = 120.0

    # Port the frontend itself listens on.
    port: int = 8080


settings = Settings()
