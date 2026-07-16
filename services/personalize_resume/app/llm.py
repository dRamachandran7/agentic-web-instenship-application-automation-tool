"""Groq call that edits a resume's raw LaTeX source directly, rephrasing and
reordering existing content to foreground what a listing is looking for.

Earlier version of this service parsed resumes into a fixed structured
schema (contact/education/experience/... as separate fields) and rendered
that into a Jinja2 LaTeX template. That broke down because real resumes
don't reliably conform to one template — a schema that fits one resume
silently drops or mangles content from another. Editing the LaTeX source
directly sidesteps that: whatever structure the user's resume already has is
preserved as-is, and the model only touches wording/ordering, not markup.

This trades away the structural validation the old approach had (bullet
counts, skill-pool checks) for generality. The one hard backstop that
remains is Tectonic itself: if the model's edits break the LaTeX, compiling
it fails loudly rather than silently shipping a broken PDF.
"""

from __future__ import annotations

import re

from groq import AsyncGroq

from .config import settings
from .models import ListingValues

SYSTEM_PROMPT = """You tailor a candidate's existing LaTeX resume to a \
specific job/internship listing, so the most relevant parts are foregrounded.

You will receive the listing's required/preferred skills, keywords, and \
values, plus the candidate's complete LaTeX resume source.

Rules:
- Do NOT invent new experience, employers, projects, dates, titles, degrees, \
tools, or skills that are not already present in the document.
- You SHOULD rephrase bullet points / \\resumeItem entries (or equivalent) to \
draw out and emphasize details already implied by that bullet's original \
wording.
- You MAY reorder bullets within a single entry, and reorder skills within a \
skills list, so the most relevant ones lead. Do not reorder or move entire \
sections, education entries, jobs, or projects relative to each other.
- You MAY lightly rewrite a summary/objective section if one exists, \
grounded only in what the resume already contains. Do not add a summary \
section if the resume doesn't already have one.
- Do NOT touch the document preamble: \\documentclass, \\usepackage lines, \
custom \\newcommand/\\renewcommand definitions, spacing/formatting commands, \
or any other structural LaTeX. Only edit the human-readable content inside \
the document body.
- The output MUST remain valid, compilable LaTeX. If you introduce or alter \
text containing characters with special meaning in LaTeX (%, &, $, #, _, {, \
}, ~, ^, \\), escape them correctly exactly as the surrounding document \
already does.
- Return the ENTIRE modified document, from \\documentclass through \
\\end{document}, unchanged outside of the content edits described above.
- Output ONLY the raw LaTeX source. No explanation, no markdown code fences, \
no commentary before or after."""

_FENCE_RE = re.compile(r"^```(?:latex|tex)?\s*\n(.*)\n```\s*$", re.DOTALL)


class LLMError(RuntimeError):
    """Raised when the Groq call fails or returns something unusable."""


def _strip_code_fence(text: str) -> str:
    """Models are told not to wrap output in code fences, but defensively
    strip them if present rather than fail the whole request over it."""
    match = _FENCE_RE.match(text.strip())
    return match.group(1) if match else text.strip()


async def personalize(resume_latex: str, values: ListingValues) -> str:
    if not settings.groq_api_key:
        raise LLMError(
            "GROQ_API_KEY is not set. Get a free key at "
            "https://console.groq.com/keys and put it in .env."
        )

    client = AsyncGroq(api_key=settings.groq_api_key)
    user_prompt = (
        f"Listing values:\n{values.model_dump_json(indent=2)}\n\n"
        f"Resume LaTeX source to personalize:\n{resume_latex}"
    )
    try:
        completion = await client.chat.completions.create(
            model=settings.groq_model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.3,
            max_tokens=settings.max_completion_tokens,
        )
    except Exception as exc:  # groq raises its own APIError subclasses
        raise LLMError(f"Groq request failed: {exc}") from exc

    raw = completion.choices[0].message.content
    if not raw or not raw.strip():
        raise LLMError("Groq returned an empty response")

    tex = _strip_code_fence(raw)
    if "\\documentclass" not in tex or "\\end{document}" not in tex:
        raise LLMError(
            "Groq's response doesn't look like a complete LaTeX document "
            "(missing \\documentclass or \\end{document})"
        )
    return tex
