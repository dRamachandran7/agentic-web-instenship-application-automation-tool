"""Request/response schemas for the analyze_listing service."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class AnalyzeRequest(BaseModel):
    """A listing to analyze — the fields search_listings scrapes in full.

    `listingId` is optional and not part of the original spec, but when the
    orchestrator has it (every listing search_listings returns does), passing
    it lets the analysis be saved back onto that listing's row instead of
    being returned and discarded.
    """

    listingId: Optional[str] = None
    title: str
    company: str
    location: str = ""
    url: str = ""
    descriptionText: str


class ListingValues(BaseModel):
    """Skills and values extracted from a listing, for personalize_resume."""

    required_skills: list[str] = Field(default_factory=list)
    preferred_skills: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    values: list[str] = Field(
        default_factory=list,
        description="Cultural/soft-skill values the employer emphasizes, e.g. 'collaborative'.",
    )
    summary: str = ""


class AnalyzeResponse(BaseModel):
    values: ListingValues
