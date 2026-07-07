"""Request/response schemas for the search_listings service.

The orchestrator sends already-parsed search parameters; this service never
parses plain text or calls an LLM — it only scrapes and returns raw listings.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class SearchParams(BaseModel):
    """User search parameters, pre-parsed by the orchestrator.

    All fields are optional. The scraper maps what it can onto Handshake's
    filters and treats the rest as best-effort keyword hints.
    """

    keywords: Optional[str] = Field(
        default=None,
        description="Free-text keywords, e.g. 'software engineering intern'.",
    )
    location: Optional[str] = Field(
        default=None, description="Desired location, e.g. 'New York, NY' or 'Remote'."
    )
    pay: Optional[str] = Field(
        default=None, description="Pay expectation, e.g. '$25/hr' or 'paid'."
    )
    hours: Optional[str] = Field(
        default=None, description="Hours / commitment, e.g. 'part-time', 'full-time'."
    )
    time_of_year: Optional[str] = Field(
        default=None, description="When the role runs, e.g. 'Summer 2026'."
    )


class Listing(BaseModel):
    """A single scraped posting. `descriptionText` is scraped in full here so
    analyze_listing does not need to re-fetch the page."""

    listingId: str
    title: str
    company: str
    location: str
    url: str
    descriptionText: str


class SearchRequest(BaseModel):
    params: SearchParams


class SearchResponse(BaseModel):
    listings: list[Listing]
