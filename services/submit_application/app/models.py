"""Request/response schemas for the submit_application service.

`resumeFile`/`coverLetterFile` arrive base64-encoded (JSON has no binary
type) exactly as personalize_resume's `PersonalizeResponse.resumeFile` is
encoded. The orchestrator passes that field straight through rather than
decoding and re-encoding it.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class SubmitRequest(BaseModel):
    listingId: str
    url: str
    resumeFile: str
    resumeFilename: str = "resume.pdf"
    coverLetterFile: Optional[str] = None
    coverLetterFilename: str = "cover_letter.pdf"


class SubmitResponse(BaseModel):
    status: str  # "submitted" | "failed"
    confirmationId: Optional[str] = None
    error: Optional[str] = None
