# search_listings

Playwright-driven microservice that scrapes Handshake for internship postings
matching pre-parsed search parameters and returns them as raw JSON. It is the
first stage of the pipeline (`search_listings → analyze_listing →
personalize_resume → submit_application`) and makes **no** LLM calls.

## Endpoint

`POST /search-listings`

```jsonc
// request
{
  "params": {
    "keywords": "software engineering intern",
    "location": "New York, NY",
    "pay": "paid",
    "hours": "part-time",
    "time_of_year": "Summer 2026"
  }
}
```

```jsonc
// response
{
  "listings": [
    {
      "listingId": "handshake:1234567",
      "title": "Software Engineering Intern",
      "company": "Acme Corp",
      "location": "New York, NY",
      "url": "https://app.joinhandshake.com/jobs/1234567",
      "descriptionText": "Full posting text scraped in full for analyze_listing..."
    }
  ]
}
```

All `params` fields are optional. The service returns `401` when the saved
session is missing/expired — re-run the auth step below.

`GET /health` reports liveness and whether a saved session exists on disk.

## Setup

```bash
cd services/search_listings
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium        # one-time browser download
```

## Configure your Handshake auth (one time)

The service never types your password. You log in once by hand and it saves the
session (cookies + localStorage) for reuse:

```bash
python -m scripts.save_auth
```

A real browser window opens. Log into Handshake — including your school's SSO
and any MFA — until you reach your dashboard, then press **Enter** in the
terminal. The session is written to `.auth/handshake.json` (gitignored).

Re-run this whenever the service starts returning `401` (sessions expire).

## Run the service

```bash
uvicorn app.main:app --reload --port 8001
```

Then:

```bash
curl -s localhost:8001/search-listings \
  -H 'content-type: application/json' \
  -d '{"params":{"keywords":"software intern","location":"Remote"}}' | jq
```

## Notes / known refinement points

- **Selectors & URL params.** Handshake has no public API and changes its
  markup periodically. Every selector and query-param name lives at the top of
  [app/scraper/handshake.py](app/scraper/handshake.py) so it can be re-pointed in
  one place after inspecting the live page (run headed via `HEADLESS=false` to
  watch). `pay`/`hours`/`time_of_year` are currently passed as keyword hints;
  mapping them onto Handshake's structured filters is a follow-up.
- **LinkedIn / Indeed** are intentionally not implemented. Per the spec they
  need rate limiting and session reuse before enabling, since they run enforced
  bot detection that can suspend a real account.
