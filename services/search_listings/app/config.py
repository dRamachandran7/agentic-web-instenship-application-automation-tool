"""Runtime configuration for the search_listings microservice.

Values are read from environment variables (a local `.env` file is loaded
automatically). Sensible defaults are provided so the service can boot with no
configuration for local development.
"""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Repo-relative default location for the saved Playwright session. Kept outside
# the app package and, crucially, gitignored — it contains live auth cookies.
_DEFAULT_STATE = Path(__file__).resolve().parents[1] / ".auth" / "handshake.json"

# Shared SQLite store at the repo root — analyze_listing points at the same
# file so it can attach analysis results to the rows search_listings writes.
_DEFAULT_DB = Path(__file__).resolve().parents[3] / "data" / "app.db"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="", extra="ignore")

    # --- Playwright / session ---
    # Path to the storageState JSON produced by scripts/save_auth.py.
    handshake_storage_state: Path = _DEFAULT_STATE
    # Run the browser headless in the service. The auth-capture script always
    # runs headed regardless of this value.
    headless: bool = True
    # Milliseconds to wait for navigations / selectors before giving up.
    nav_timeout_ms: int = 30_000

    # --- Handshake ---
    handshake_base_url: str = "https://app.joinhandshake.com"

    # --- Search behaviour ---
    # Hard cap on listings returned per request, so we don't paginate forever.
    max_listings: int = 25

    # --- Storage ---
    # Shared SQLite file where scraped listings are persisted.
    db_path: Path = _DEFAULT_DB

    @property
    def storage_state_path(self) -> Path:
        return Path(self.handshake_storage_state)


settings = Settings()
