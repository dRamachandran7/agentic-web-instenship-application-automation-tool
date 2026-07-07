"""Common scraper contract and errors.

When LinkedIn/Indeed are added, they implement `Scraper` and get wired into the
endpoint the same way Handshake is. Per the spec, those platforms must sit
behind rate limiting and session reuse before being enabled.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from playwright.async_api import Browser

from ..models import Listing, SearchParams


class AuthError(RuntimeError):
    """Raised when the saved session is missing or expired.

    The caller should surface this so the user knows to re-run the auth-capture
    script rather than treating it as a transient scrape failure.
    """


class Scraper(ABC):
    #: Stable identifier used to namespace listing ids, e.g. "handshake".
    platform: str

    def __init__(self, browser: Browser) -> None:
        self.browser = browser

    @abstractmethod
    async def search(self, params: SearchParams) -> list[Listing]:
        """Return listings matching `params`. Must raise `AuthError` if the
        session is not authenticated."""
        raise NotImplementedError
