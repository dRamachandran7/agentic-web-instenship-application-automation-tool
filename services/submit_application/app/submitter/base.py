"""Common submitter contract and errors.

When LinkedIn/Indeed are added, they implement `Submitter` and get registered
in `main.SUBMITTERS` the same way Handshake is. Per the spec, those platforms
must sit behind rate limiting and session reuse before being enabled.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

from playwright.async_api import Browser

from ..profile import UserProfile


class AuthError(RuntimeError):
    """Raised when the saved session is missing or expired.

    The caller should surface this so the user knows to re-run the auth-capture
    script rather than treating it as a failed submission.
    """


class SubmitError(RuntimeError):
    """Raised when the application flow itself could not be completed (no
    apply button, unrecognized/external form, missing required fields, etc.).
    Distinct from AuthError: the session is fine, the submission isn't."""


@dataclass
class SubmitResult:
    confirmation_id: Optional[str] = None


class Submitter(ABC):
    #: Stable identifier matching the `<platform>:<id>` prefix search_listings
    #: puts on `listingId`, used to route a request to the right submitter.
    platform: str

    def __init__(self, browser: Browser) -> None:
        self.browser = browser

    @abstractmethod
    async def submit(
        self,
        *,
        url: str,
        resume_buffer: bytes,
        resume_filename: str,
        cover_letter_buffer: Optional[bytes],
        cover_letter_filename: str,
        profile: UserProfile,
    ) -> SubmitResult:
        """Submit the application. Must raise `AuthError` if the session is
        not authenticated, `SubmitError` if the flow could not be completed."""
        raise NotImplementedError
