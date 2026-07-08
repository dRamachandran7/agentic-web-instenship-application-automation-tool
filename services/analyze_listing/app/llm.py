"""Groq call that extracts a listing's key skills/values.

Uses Groq's OpenAI-compatible JSON mode so the model's response can be parsed
straight into `ListingValues` without a second cleanup pass.
"""

from __future__ import annotations

import json

from groq import AsyncGroq

from .config import settings
from .models import ListingValues

SYSTEM_PROMPT = """You read job/internship postings and extract what the \
employer is looking for, so a candidate's resume can be tailored to this \
specific listing.

Given a title, company, location, and the full posting text, return a JSON \
object with exactly these keys:
- "required_skills": array of strings — technical skills, tools, or \
qualifications explicitly required.
- "preferred_skills": array of strings — skills described as "nice to have" \
or preferred but not required.
- "keywords": array of strings — other notable domain terms, methodologies, \
or certifications worth echoing back in a resume.
- "values": array of strings — cultural or soft-skill values the employer \
emphasizes (e.g. "collaborative", "fast-paced", "detail-oriented").
- "summary": string — one or two sentence summary of what this role is \
fundamentally about.

Only include what is actually stated or strongly implied in the posting. Do \
not invent skills or values that aren't mentioned. Return ONLY the JSON \
object, no other text."""


class LLMError(RuntimeError):
    """Raised when the Groq call fails or returns something unusable."""


async def analyze(title: str, company: str, location: str, description_text: str) -> ListingValues:
    if not settings.groq_api_key:
        raise LLMError(
            "GROQ_API_KEY is not set. Get a free key at "
            "https://console.groq.com/keys and put it in .env."
        )

    client = AsyncGroq(api_key=settings.groq_api_key)
    user_prompt = (
        f"Title: {title}\nCompany: {company}\nLocation: {location}\n\n"
        f"Posting:\n{description_text}"
    )
    try:
        completion = await client.chat.completions.create(
            model=settings.groq_model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0.2,
        )
    except Exception as exc:  # groq raises its own APIError subclasses
        raise LLMError(f"Groq request failed: {exc}") from exc

    raw = completion.choices[0].message.content
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise LLMError(f"Groq returned non-JSON content: {raw!r}") from exc

    return ListingValues.model_validate(data)
