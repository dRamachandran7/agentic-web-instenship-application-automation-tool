"""search_listings microservice.

Exposes `POST /search-listings`. The orchestrator calls it with pre-parsed
search parameters; the service scrapes Handshake with Playwright and returns raw
listings. No LLM calls happen here.

A single browser is launched at startup and reused across requests; each request
gets a fresh context built from the saved `storageState`, so sessions are reused
without leaking cookies between concurrent requests.
"""

from __future__ import annotations

import json
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from playwright.async_api import async_playwright

from . import storage
from .config import settings
from .models import SearchRequest, SearchResponse
from .scraper.base import AuthError
from .scraper.handshake import HandshakeScraper


@asynccontextmanager
async def lifespan(app: FastAPI):
    storage.init_db()
    playwright = await async_playwright().start()
    browser = await playwright.chromium.launch(headless=settings.headless)
    app.state.playwright = playwright
    app.state.browser = browser
    try:
        yield
    finally:
        await browser.close()
        await playwright.stop()


app = FastAPI(title="search_listings", lifespan=lifespan)


@app.get("/health")
async def health() -> dict[str, object]:
    """Liveness plus whether a saved session is present on disk."""
    return {
        "status": "ok",
        "storage_state_present": settings.storage_state_path.exists(),
    }


@app.post("/search-listings", response_model=SearchResponse)
async def search_listings(request: SearchRequest) -> SearchResponse:
    scraper = HandshakeScraper(app.state.browser)
    try:
        listings = await scraper.search(request.params)
    except AuthError as exc:
        # 401 so the orchestrator can distinguish "re-auth needed" from a
        # transient scrape failure.
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    storage.save_listings(listings)
    return SearchResponse(listings=listings)


def _row_to_dict(row) -> dict[str, object]:
    d = dict(row)
    d["values"] = json.loads(d.pop("values_json")) if d.get("values_json") else None
    return d


@app.get("/listings")
async def list_saved_listings() -> list[dict[str, object]]:
    """Every listing persisted so far, most recently scraped first."""
    return [_row_to_dict(row) for row in storage.get_listings()]


@app.get("/listings/{listing_id}")
async def get_saved_listing(listing_id: str) -> dict[str, object]:
    row = storage.get_listing(listing_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"No saved listing with id {listing_id!r}")
    return _row_to_dict(row)
