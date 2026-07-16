"""Handshake application submitter.

Auth: reuses the same Playwright `storageState` search_listings captured via
`scripts/save_auth.py` (see that service's README) — this service never logs
in itself.

DOM caveat: like search_listings' scraper, Handshake's apply UI has no public
spec and changes periodically. Every selector lives in the constants below so
it can be re-pointed in one place after inspecting the live apply flow.

Scope: this handles Handshake's own in-app apply form (resume/cover-letter
upload plus a handful of text fields/screening questions). Postings that
route to an external ATS ("Apply on company site") are detected and reported
as a failure rather than guessed at — automating an arbitrary third-party
site is out of scope.
"""

from __future__ import annotations

import re
from typing import Optional

from playwright.async_api import BrowserContext, Page, TimeoutError as PWTimeout

from ..config import settings
from ..profile import UserProfile
from .base import AuthError, SubmitError, SubmitResult, Submitter

# --- Selectors (verify against live DOM) ------------------------------------
LOGIN_MARKERS = ("/login", "/employer-login", "/oauth")

APPLY_BUTTON_SELECTORS = [
    'button:has-text("Apply")',
    'a:has-text("Apply")',
]

# Body text that marks a posting as routing to an external ATS rather than
# Handshake's own apply form.
EXTERNAL_APPLY_MARKERS = (
    "apply on company site",
    "apply externally",
    "apply on employer site",
    "continue to employer",
)

RESUME_INPUT_SELECTORS = [
    'input[type="file"][name*="resume" i]',
    'input[type="file"][aria-label*="resume" i]',
    'input[type="file"]',
]
COVER_LETTER_INPUT_SELECTORS = [
    'input[type="file"][name*="cover" i]',
    'input[type="file"][aria-label*="cover" i]',
]

EMAIL_INPUT_SELECTORS = ['input[type="email"]']
PHONE_INPUT_SELECTORS = ['input[type="tel"]', 'input[name*="phone" i]']
NAME_INPUT_SELECTORS = [
    'input[name*="name" i]:not([type="email"])',
    'input[aria-label*="name" i]',
]

SUBMIT_BUTTON_SELECTORS = [
    'button[type="submit"]:has-text("Submit")',
    'button:has-text("Submit Application")',
    'button:has-text("Submit")',
]

# Loose match on purpose: Handshake's exact confirmation copy isn't public and
# is the first thing to re-check if submissions start reporting false failures.
CONFIRMATION_TEXT_RE = re.compile(
    r"application (?:submitted|received)|successfully applied", re.I
)
CONFIRMATION_ID_RE = re.compile(r"confirmation\s*(?:number|#|id)?[:\s]+([A-Za-z0-9-]+)", re.I)


class HandshakeSubmitter(Submitter):
    platform = "handshake"

    async def _new_context(self) -> BrowserContext:
        state = settings.storage_state_path
        if not state.exists():
            raise AuthError(
                f"No saved Handshake session at {state}. "
                "Run `python -m scripts.save_auth` in search_listings to log in and capture one."
            )
        ctx = await self.browser.new_context(storage_state=str(state))
        ctx.set_default_timeout(settings.nav_timeout_ms)
        return ctx

    @staticmethod
    def _assert_authenticated(page: Page) -> None:
        url = page.url
        if any(marker in url for marker in LOGIN_MARKERS):
            raise AuthError(
                "Handshake redirected to a login page — the saved session has "
                "expired. Re-run `python -m scripts.save_auth` in search_listings."
            )

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
        ctx = await self._new_context()
        try:
            page = await ctx.new_page()
            await page.goto(url, wait_until="domcontentloaded")
            self._assert_authenticated(page)

            await self._open_apply_form(page)
            await self._attach_files(
                page, resume_buffer, resume_filename, cover_letter_buffer, cover_letter_filename
            )
            await self._fill_profile_fields(page, profile)
            return await self._submit_and_confirm(page)
        finally:
            await ctx.close()

    async def _open_apply_form(self, page: Page) -> None:
        body_text = (await page.inner_text("body")).lower()
        if any(marker in body_text for marker in EXTERNAL_APPLY_MARKERS):
            raise SubmitError(
                "This posting routes to an external application site — not automated by this service."
            )

        button = await _first_visible(page, APPLY_BUTTON_SELECTORS)
        if button is None:
            raise SubmitError("No 'Apply' button found on the listing page.")
        await button.click()

        # Applying may open a modal / route swap rather than a full navigation;
        # wait for a file input to appear as the signal the form is ready.
        try:
            await page.wait_for_selector(RESUME_INPUT_SELECTORS[-1], state="attached")
        except PWTimeout as exc:
            raise SubmitError("Apply form did not render a resume upload field.") from exc

    async def _attach_files(
        self,
        page: Page,
        resume_buffer: bytes,
        resume_filename: str,
        cover_letter_buffer: Optional[bytes],
        cover_letter_filename: str,
    ) -> None:
        resume_input = await _first_locator(page, RESUME_INPUT_SELECTORS)
        if resume_input is None:
            raise SubmitError("Could not locate a resume upload field on the apply form.")
        # setInputFiles accepts an in-memory buffer directly — no temp file needed.
        await resume_input.set_input_files(
            {"name": resume_filename, "mimeType": "application/pdf", "buffer": resume_buffer}
        )

        if cover_letter_buffer is not None:
            cover_input = await _first_locator(page, COVER_LETTER_INPUT_SELECTORS)
            if cover_input is not None:
                await cover_input.set_input_files(
                    {
                        "name": cover_letter_filename,
                        "mimeType": "application/pdf",
                        "buffer": cover_letter_buffer,
                    }
                )
            # No cover-letter field on this posting: it wasn't required, skip.

    async def _fill_profile_fields(self, page: Page, profile: UserProfile) -> None:
        """Best-effort fill of contact fields the form exposes. Screening
        questions are matched by substring against `profile.screening_answers`
        keys; anything unmatched is left blank for the page's own validation
        to surface (as a failed submit) rather than guessed at."""
        await _fill_first_empty(page, EMAIL_INPUT_SELECTORS, profile.email)
        if profile.phone:
            await _fill_first_empty(page, PHONE_INPUT_SELECTORS, profile.phone)
        await _fill_first_empty(page, NAME_INPUT_SELECTORS, profile.full_name)

        if not profile.screening_answers:
            return
        for field in await page.query_selector_all('textarea, input[type="text"]'):
            if (await field.input_value()).strip():
                continue
            label = await _label_text(page, field)
            if not label:
                continue
            answer = _match_screening_answer(label, profile.screening_answers)
            if answer:
                await field.fill(answer)

    async def _submit_and_confirm(self, page: Page) -> SubmitResult:
        button = await _first_visible(page, SUBMIT_BUTTON_SELECTORS)
        if button is None:
            raise SubmitError("No submit button found on the apply form.")
        await button.click()

        try:
            await page.wait_for_function(
                "(re) => new RegExp(re, 'i').test(document.body.innerText)",
                arg=CONFIRMATION_TEXT_RE.pattern,
                timeout=settings.nav_timeout_ms,
            )
        except PWTimeout as exc:
            raise SubmitError(
                "No confirmation appeared after submitting — the form likely has "
                "unfilled required fields this service couldn't determine."
            ) from exc

        body_text = await page.inner_text("body")
        match = CONFIRMATION_ID_RE.search(body_text)
        return SubmitResult(confirmation_id=match.group(1) if match else None)


async def _first_visible(page: Page, selectors: list[str]):
    for selector in selectors:
        for el in await page.query_selector_all(selector):
            if await el.is_visible():
                return el
    return None


async def _first_locator(page: Page, selectors: list[str]):
    for selector in selectors:
        el = await page.query_selector(selector)
        if el is not None:
            return el
    return None


async def _fill_first_empty(page: Page, selectors: list[str], value: str) -> None:
    if not value:
        return
    el = await _first_locator(page, selectors)
    if el is None:
        return
    if (await el.input_value()).strip():
        return  # already populated, e.g. pre-filled from the user's Handshake profile
    await el.fill(value)


async def _label_text(page: Page, element) -> str:
    """Best-effort label lookup: an explicit <label for>, else aria-label,
    else placeholder."""
    field_id = await element.get_attribute("id")
    if field_id:
        label = await page.query_selector(f'label[for="{field_id}"]')
        if label:
            return (await label.inner_text()).strip()
    aria_label = await element.get_attribute("aria-label")
    if aria_label:
        return aria_label.strip()
    placeholder = await element.get_attribute("placeholder")
    return placeholder.strip() if placeholder else ""


def _match_screening_answer(label: str, answers: dict[str, str]) -> Optional[str]:
    label_lower = label.lower()
    for question, answer in answers.items():
        if question.lower() in label_lower:
            return answer
    return None
