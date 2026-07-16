"""The user's stored profile data: contact info and screening-question
answers used to fill out whatever fields an apply form asks for beyond the
resume/cover-letter upload.

Kept as a local JSON file (like the Playwright `storageState`) rather than in
the shared SQLite store, since it's personal data with no natural per-listing
row to live on. See `.profile/profile.example.json` for the shape.
"""

from __future__ import annotations

import json

from pydantic import BaseModel, Field

from .config import settings


class ProfileError(RuntimeError):
    """Raised when the user's profile data is missing or invalid."""


class UserProfile(BaseModel):
    full_name: str
    email: str
    phone: str = ""
    linkedin_url: str = ""
    website_url: str = ""
    # Best-effort question -> answer lookup for screening questions. Keys are
    # matched as case-insensitive substrings against a form field's label, so
    # keep them short and distinctive, e.g. "sponsorship" or "authorized to work".
    screening_answers: dict[str, str] = Field(default_factory=dict)


def load_profile() -> UserProfile:
    path = settings.profile_path
    if not path.exists():
        raise ProfileError(
            f"No profile data at {path}. Copy .profile/profile.example.json to "
            f"{path.name} in the same directory and fill in your contact info."
        )
    data = json.loads(path.read_text(encoding="utf-8"))
    return UserProfile.model_validate(data)
