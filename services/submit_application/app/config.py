"""Runtime configuration for the submit_application microservice.

Values are read from environment variables (a local `.env` file is loaded
automatically). Sensible defaults are provided so the service can boot with no
configuration for local development.
"""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# submit_application reuses the *same* Handshake session search_listings
# captured — per the spec it "reuses the same per-platform storageState
# session established by search_listings" rather than logging in again.
_DEFAULT_STATE = (
    Path(__file__).resolve().parents[2] / "search_listings" / ".auth" / "handshake.json"
)

# Where the user's contact info / screening-question answers live. Kept
# outside the app package and gitignored, like the storageState file, since
# it holds personal data.
_DEFAULT_PROFILE = Path(__file__).resolve().parents[1] / ".profile" / "profile.json"

# Shared SQLite store at the repo root — search_listings/analyze_listing also
# read/write this file, so submission outcomes can be attached to the same row.
_DEFAULT_DB = Path(__file__).resolve().parents[3] / "data" / "app.db"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="", extra="ignore")

    # --- Playwright / session ---
    handshake_storage_state: Path = _DEFAULT_STATE
    headless: bool = True
    nav_timeout_ms: int = 30_000

    # --- Handshake ---
    handshake_base_url: str = "https://app.joinhandshake.com"

    # --- Profile ---
    profile_path: Path = _DEFAULT_PROFILE

    # --- Storage ---
    db_path: Path = _DEFAULT_DB

    @property
    def storage_state_path(self) -> Path:
        return Path(self.handshake_storage_state)


settings = Settings()
