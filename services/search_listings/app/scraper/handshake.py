"""Handshake job-search scraper.

Auth: the service never logs in interactively. It loads a Playwright
`storageState` (cookies + localStorage) captured once by
`scripts/save_auth.py`. This avoids repeated-login bot signals and is fast on
subsequent runs.

DOM caveat: Handshake ships no public scraping API and changes its markup
periodically. Every selector and query-param name the scraper depends on is
collected in the constants below so it can be re-pointed in one place after
inspecting the live page. Where a single selector is risky, `_first_text` tries
a list of candidates and falls back to broad heuristics.
"""

from __future__ import annotations

import re
from urllib.parse import urlencode

from playwright.async_api import BrowserContext, Page, TimeoutError as PWTimeout

from ..config import settings
from ..models import Listing, SearchParams
from .base import AuthError, Scraper

# --- URL construction -------------------------------------------------------
# Student job search entry point. `query` = keywords, `location` = place.
# Verify these param names against the live search URL and adjust as needed.
JOB_SEARCH_PATH = "/job-search"
QUERY_PARAM_KEYWORDS = "query"
QUERY_PARAM_LOCATION = "location"

# Matches a posting url/href and captures the numeric listing id, covering every
# form Handshake uses: result-card hrefs (/jobs/, /postings/) and the canonical
# detail route the app routes to on click (/job-search/<id>).
LISTING_ID_RE = re.compile(r"/(?:jobs|postings|job-search)/(\d+)")

# --- Selectors (verify against live DOM) ------------------------------------
# A logged-out session lands on one of these; used to detect an expired state.
LOGIN_MARKERS = ("/login", "/employer-login", "/oauth")

# Any anchor pointing at a posting. We collect these off the results list
# rather than depending on a specific card-container class, which changes often.
RESULT_LINK_SELECTOR = (
    'a[href*="/jobs/"], a[href*="/postings/"], a[href*="/job-search/"]'
)

# The entire posting (company, title, "At a glance", description, employer info)
# renders inside this one container. We scope field lookups to it and use its
# full text as the description, rather than hunting fragile per-field selectors.
DETAIL_CONTAINER_SELECTOR = '[data-hook="right-content"]'

# Detail-page fields: each entry is a list of candidate selectors tried in order.
DETAIL_TITLE_SELECTORS = [f"{DETAIL_CONTAINER_SELECTOR} h1", "h1"]
DETAIL_COMPANY_SELECTORS = [
    # Handshake exposes no company data-hook; the employer link near the top of
    # the container is the stable anchor (employer profile links are /e/<id>).
    # Container-scoped + :first keeps us off the "Similar Jobs" / "Alumni"
    # employer links lower on the page.
    f'{DETAIL_CONTAINER_SELECTOR} a[href*="/e/"]',
    'a[href*="/e/"]',
]
DETAIL_LOCATION_SELECTORS = [
    # No dedicated location element either — best-effort only. When it misses,
    # the location still reaches analyze_listing inside the full description text.
    '[data-hook="job-location"]',
    '[class*="location"]',
]
# Full container text: comprehensive and robust. Fallbacks cover markup drift.
DETAIL_DESCRIPTION_SELECTORS = [DETAIL_CONTAINER_SELECTOR, "article", "main"]


class HandshakeScraper(Scraper):
    platform = "handshake"

    def _build_search_url(self, params: SearchParams) -> str:
        query: dict[str, str] = {}
        if params.keywords:
            query[QUERY_PARAM_KEYWORDS] = params.keywords
        if params.location:
            query[QUERY_PARAM_LOCATION] = params.location
        base = settings.handshake_base_url.rstrip("/")
        qs = f"?{urlencode(query)}" if query else ""
        return f"{base}{JOB_SEARCH_PATH}{qs}"

    def _detail_url(self, listing_id: str) -> str:
        # Handshake's canonical detail route is /job-search/<id> (what the app
        # routes to on click). /jobs/<id> renders nothing, so don't use it.
        base = settings.handshake_base_url.rstrip("/")
        return f"{base}{JOB_SEARCH_PATH}/{listing_id}"

    async def _new_context(self) -> BrowserContext:
        state = settings.storage_state_path
        if not state.exists():
            raise AuthError(
                f"No saved Handshake session at {state}. "
                "Run `python -m scripts.save_auth` to log in and capture one."
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
                "expired. Re-run `python -m scripts.save_auth`."
            )

    async def search(self, params: SearchParams) -> list[Listing]:
        ctx = await self._new_context()
        try:
            # Handshake renders results and the detail panel in one SPA view:
            # `/job-search/<id>` is the search page *plus* a panel, not a
            # standalone page. So we load the search page once and click each
            # result to swap the panel in place — no per-listing tab or reload.
            page = await ctx.new_page()
            await page.goto(self._build_search_url(params), wait_until="domcontentloaded")
            self._assert_authenticated(page)

            listing_ids = await self._collect_listing_ids(page)
            listings: list[Listing] = []
            for listing_id in listing_ids[: settings.max_listings]:
                listing = await self._open_and_scrape(page, listing_id)
                if listing is not None:
                    listings.append(listing)
            return listings
        finally:
            await ctx.close()

    async def _collect_listing_ids(self, page: Page) -> list[str]:
        """Return de-duplicated posting ids in result order."""
        try:
            # SPA: wait for result links to actually render, not just for the
            # initial document.
            await page.wait_for_selector(RESULT_LINK_SELECTOR, state="visible")
        except PWTimeout:
            return []  # No results for this query.

        hrefs = await page.eval_on_selector_all(
            RESULT_LINK_SELECTOR,
            "els => els.map(e => e.getAttribute('href'))",
        )
        ids: list[str] = []
        seen: set[str] = set()
        for href in hrefs:
            if not href:
                continue
            match = LISTING_ID_RE.search(href)
            if match and match.group(1) not in seen:
                seen.add(match.group(1))
                ids.append(match.group(1))
        return ids

    async def _open_and_scrape(self, page: Page, listing_id: str) -> Listing | None:
        """Open a listing's detail panel on the shared search page and scrape it.

        Prefers clicking the result card (client-side route swap, no reload);
        falls back to navigating the same page to the detail URL if the card
        isn't in the DOM (e.g. a virtualized list scrolled it out).
        """
        url = self._detail_url(listing_id)
        # Snapshot the currently-shown title so we can detect the panel actually
        # swapping to this listing (the container persists between listings).
        prev_title = await _first_text(page, DETAIL_TITLE_SELECTORS)

        card = await page.query_selector(f'a[href*="{listing_id}"]')
        if card is not None:
            await card.click()
        else:
            await page.goto(url, wait_until="domcontentloaded")
        self._assert_authenticated(page)

        # Wait for the route to reflect this listing, then for its panel to
        # actually re-render (title changes), so we don't scrape the prior post.
        try:
            await page.wait_for_url(re.compile(rf"/{listing_id}(?:[/?#]|$)"))
        except PWTimeout:
            pass
        await _wait_for_panel(page, prev_title)

        title = await _first_text(page, DETAIL_TITLE_SELECTORS)
        company = await _first_text(page, DETAIL_COMPANY_SELECTORS)
        location = await _first_text(page, DETAIL_LOCATION_SELECTORS)
        description = await _first_text(page, DETAIL_DESCRIPTION_SELECTORS)

        # No title/description usually means the panel didn't render (rate-limited,
        # deleted, or selector drift). Skip rather than emit an empty listing.
        if not title and not description:
            return None

        return Listing(
            listingId=f"{self.platform}:{listing_id}",
            title=title or "(unknown title)",
            company=company or "(unknown company)",
            location=location or "",
            url=url,
            descriptionText=description or "",
        )


# JS predicate: the panel title is non-empty and differs from the prior
# listing's title — i.e. the panel has actually swapped to the new posting.
# Uses an unquoted attribute selector to avoid nested-quote escaping.
_PANEL_SWAPPED_JS = """
(prev) => {
  const h = document.querySelector('[data-hook=right-content] h1')
         || document.querySelector('h1');
  const t = h && h.innerText ? h.innerText.trim() : '';
  return t.length > 0 && t !== prev;
}
"""


async def _wait_for_panel(page: Page, prev_title: str) -> None:
    """Wait until the detail panel reflects the newly-selected listing.

    Falls back to waiting for the container to be present, so a listing that
    genuinely shares a title with the previous one still gets scraped rather
    than blocking on the title-change predicate.
    """
    try:
        await page.wait_for_function(_PANEL_SWAPPED_JS, arg=prev_title)
    except PWTimeout:
        await _wait_for_any(page, [DETAIL_CONTAINER_SELECTOR, "h1"])


async def _wait_for_any(page: Page, selectors: list[str]) -> bool:
    """Wait until any of `selectors` is visible. Returns False on timeout.

    Selectors are raced as a single CSS list so the wait costs one timeout, not
    one per candidate. A timeout is non-fatal — callers still attempt to scrape,
    since a drifted selector shouldn't block the fields that did render.
    """
    try:
        await page.wait_for_selector(", ".join(selectors), state="visible")
        return True
    except PWTimeout:
        return False


async def _first_text(page: Page, selectors: list[str]) -> str:
    """Return trimmed innerText of the first matching element with non-empty
    text, else "".

    Checks every element matching a selector (not just the first DOM match)
    before moving to the next candidate selector: some selectors match an
    icon-only element (e.g. a logo link with no text) ahead of the one that
    actually holds the text in DOM order.
    """
    for selector in selectors:
        for el in await page.query_selector_all(selector):
            text = (await el.inner_text()).strip()
            if text:
                return text
    return ""
