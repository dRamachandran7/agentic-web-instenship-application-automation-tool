# submit_application

Playwright-driven microservice that takes the personalized resume (and
optional cover letter) produced by `personalize_resume` and submits the
application on the platform the listing came from. It is the fourth and
final stage of the pipeline (`search_listings → analyze_listing →
personalize_resume → submit_application`) and makes **no** LLM calls — like
`search_listings`, it is the "hands" layer, not the "brain".

## Endpoint

`POST /submit-application`

```jsonc
// request
{
  "listingId": "handshake:1234567",
  "url": "https://app.joinhandshake.com/job-search/1234567",
  "resumeFile": "<base64-encoded PDF bytes>",   // personalize_resume's `resumeFile`, passed straight through
  "resumeFilename": "resume.pdf",               // personalize_resume's `filename`
  "coverLetterFile": null,                       // optional, same base64 shape
  "coverLetterFilename": "cover_letter.pdf"
}
```

```jsonc
// response
{
  "status": "submitted",       // or "failed"
  "confirmationId": "AB12CD",  // best-effort, present only if the confirmation page exposed one
  "error": null                // present when status is "failed"
}
```

`resumeFile`/`coverLetterFile` are base64-encoded PDF bytes — the same
encoding `personalize_resume` returns them in — decoded here into in-memory
buffers and attached via Playwright's `setInputFiles()`, so no temp files are
written to disk.

A per-listing submission failure (no apply button, an external application
flow, unfilled required fields) is returned as `200 {"status": "failed",
"error": "..."}`, not an HTTP error, so the orchestrator can log the outcome
and continue to the next listing. `401` is reserved for an expired/missing
Handshake session; `400` for a listing whose platform has no submitter, or a
missing profile file.

Every submission attempt is also recorded on the shared SQLite store at
`data/app.db` (repo root), on the row `search_listings` created for that
`listingId` — `submission_status`, `confirmation_id`, `submission_error`,
`submitted_at`.

`GET /health` reports liveness plus whether a saved session and profile file
are present.

## Scope

Only Handshake's own in-app apply form is automated: resume/cover-letter
upload plus a handful of text fields and screening questions, filled from
`.profile/profile.json`. Postings that route to an external ATS ("Apply on
company site") are detected and reported as a failed submission rather than
guessed at — automating an arbitrary third-party site is out of scope, same
reasoning as `search_listings` not touching LinkedIn/Indeed yet.

## Setup

```bash
cd services/submit_application
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium        # one-time browser download
```

### Session

This service does **not** capture its own Handshake login — it reuses the
session `search_listings` already captured. If you haven't run that yet:

```bash
cd ../search_listings
python -m scripts.save_auth
```

By default `submit_application` reads `../search_listings/.auth/handshake.json`
directly; point `HANDSHAKE_STORAGE_STATE` elsewhere if you've moved it.

### Profile

Copy the example and fill in your contact info and any screening-question
answers you want auto-filled:

```bash
cp .profile/profile.example.json .profile/profile.json
```

```jsonc
{
  "full_name": "Jane Student",
  "email": "jane@example.edu",
  "phone": "555-123-4567",
  "linkedin_url": "https://linkedin.com/in/janestudent",
  "website_url": "",
  "screening_answers": {
    // key is matched as a case-insensitive substring against a form
    // field's label — keep keys short and distinctive.
    "sponsorship": "No, I do not require sponsorship",
    "authorized to work": "Yes"
  }
}
```

Fields the form asks for that aren't covered here are left blank; if a
required field goes unfilled, the submit will fail rather than send a
partially-completed application.

## Run the service

```bash
uvicorn app.main:app --reload --port 8004
```

```bash
python3 -c "
import base64, json
json.dump({
    'listingId': 'handshake:1234567',
    'url': 'https://app.joinhandshake.com/job-search/1234567',
    'resumeFile': base64.b64encode(open('/tmp/resume.pdf', 'rb').read()).decode(),
    'resumeFilename': 'resume.pdf',
}, open('/tmp/request.json', 'w'))
"

curl -s localhost:8004/submit-application \
  -H 'content-type: application/json' \
  -d @/tmp/request.json | jq
```

## Notes / known refinement points

- **Selectors.** Like `search_listings`, Handshake's apply-form markup has no
  public spec. Every selector lives at the top of
  [app/submitter/handshake.py](app/submitter/handshake.py) so it can be
  re-pointed in one place after inspecting a live apply flow (run headed via
  `HEADLESS=false` to watch).
- **Confirmation detection** is a loose text match (`"application
  submitted"`, `"successfully applied"`) since Handshake's exact copy isn't
  public — the first thing to check if submissions report false failures.
  `confirmationId` extraction is similarly best-effort and often `null`.
- **External applications and LinkedIn/Indeed** are intentionally not
  automated, for the same bot-detection/scope reasons `search_listings`
  gives for those platforms.
