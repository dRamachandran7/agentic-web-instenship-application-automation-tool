"""analyze_listing microservice.

Exposes `POST /analyze-listing`. Takes a listing's scraped fields and makes
one Groq call to extract the skills/values personalize_resume needs. Makes no
Playwright calls itself — that's search_listings' job.
"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException

from . import storage
from .config import settings
from .llm import LLMError, analyze
from .models import AnalyzeRequest, AnalyzeResponse

app = FastAPI(title="analyze_listing")


@app.get("/health")
async def health() -> dict[str, object]:
    return {"status": "ok", "groq_api_key_present": bool(settings.groq_api_key)}


@app.post("/analyze-listing", response_model=AnalyzeResponse)
async def analyze_listing(request: AnalyzeRequest) -> AnalyzeResponse:
    try:
        values = await analyze(
            title=request.title,
            company=request.company,
            location=request.location,
            description_text=request.descriptionText,
        )
    except LLMError as exc:
        # 502: the request was fine, the upstream Groq call is what failed.
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    if request.listingId:
        storage.save_analysis(request.listingId, values.model_dump())

    return AnalyzeResponse(values=values)
