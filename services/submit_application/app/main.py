"""submit_application microservice.

Exposes `POST /submit-application`. Takes a listing id/url plus the
personalized resume (and optional cover letter) produced by
personalize_resume and submits the application with Playwright. Like
search_listings, this is the "hands" layer — it makes no LLM calls of its own.

A single browser is launched at startup and reused across requests; each
request gets a fresh context built from the saved `storageState`, mirroring
search_listings.
"""

from __future__ import annotations

import base64
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from playwright.async_api import async_playwright

from . import storage
from .config import settings
from .models import SubmitRequest, SubmitResponse
from .profile import ProfileError, load_profile
from .submitter.base import AuthError, SubmitError
from .submitter.handshake import HandshakeSubmitter

# Platform -> Submitter, keyed by the prefix search_listings puts on
# `listingId` (e.g. "handshake:1234567"). LinkedIn/Indeed go here once added,
# per the spec, behind rate limiting and session reuse.
SUBMITTERS = {
    "handshake": HandshakeSubmitter,
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    playwright = await async_playwright().start()
    browser = await playwright.chromium.launch(headless=settings.headless)
    app.state.playwright = playwright
    app.state.browser = browser
    try:
        yield
    finally:
        await browser.close()
        await playwright.stop()


app = FastAPI(title="submit_application", lifespan=lifespan)


@app.get("/health")
async def health() -> dict[str, object]:
    return {
        "status": "ok",
        "storage_state_present": settings.storage_state_path.exists(),
        "profile_present": settings.profile_path.exists(),
    }


def _resolve_submitter(listing_id: str):
    platform = listing_id.split(":", 1)[0] if ":" in listing_id else None
    return SUBMITTERS.get(platform) if platform else None


@app.post("/submit-application", response_model=SubmitResponse)
async def submit_application(request: SubmitRequest) -> SubmitResponse:
    submitter_cls = _resolve_submitter(request.listingId)
    if submitter_cls is None:
        raise HTTPException(
            status_code=400,
            detail=f"No submitter for listingId {request.listingId!r} "
            "(expected a '<platform>:<id>' prefix, e.g. 'handshake:1234567').",
        )

    try:
        profile = load_profile()
    except ProfileError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    resume_buffer = base64.b64decode(request.resumeFile)
    cover_letter_buffer = (
        base64.b64decode(request.coverLetterFile) if request.coverLetterFile else None
    )

    submitter = submitter_cls(app.state.browser)
    try:
        result = await submitter.submit(
            url=request.url,
            resume_buffer=resume_buffer,
            resume_filename=request.resumeFilename,
            cover_letter_buffer=cover_letter_buffer,
            cover_letter_filename=request.coverLetterFilename,
            profile=profile,
        )
    except AuthError as exc:
        # 401 so the orchestrator can distinguish "re-auth needed" from a
        # failed submission.
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except SubmitError as exc:
        # A per-listing failure, not an infra problem — return 200 with
        # status="failed" so the orchestrator can log it and move on to the
        # next listing rather than aborting the whole run.
        storage.save_submission(request.listingId, status="failed", error=str(exc))
        return SubmitResponse(status="failed", error=str(exc))

    storage.save_submission(
        request.listingId, status="submitted", confirmation_id=result.confirmation_id
    )
    return SubmitResponse(status="submitted", confirmationId=result.confirmation_id)
