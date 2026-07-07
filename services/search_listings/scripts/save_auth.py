"""One-time interactive login to capture a Handshake session.

Opens a real (headed) browser, lets you log in by hand — including any
university SSO / MFA — then saves the resulting cookies + localStorage to the
path the service reads (`settings.storage_state_path`). Re-run this whenever the
service returns a 401 (session expired).

Usage (from services/search_listings/):
    python -m scripts.save_auth
"""

from __future__ import annotations

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

# Allow running as `python -m scripts.save_auth` from the service root.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import settings  # noqa: E402


def main() -> None:
    out_path = settings.storage_state_path
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        page.goto(settings.handshake_base_url)

        print("\n" + "=" * 68)
        print("A browser window has opened. Log into Handshake there,")
        print("including any school SSO / MFA, until you reach your dashboard.")
        print(f"Session will be saved to: {out_path}")
        print("=" * 68)
        input("\nWhen you are fully logged in, press Enter here to save... ")

        context.storage_state(path=str(out_path))
        browser.close()

    print(f"\nSaved session to {out_path}. The service will now reuse it.")


if __name__ == "__main__":
    main()
