# frontend

A single-page [NiceGUI](https://nicegui.io/) app that is both the UI and the
orchestrator: it takes a resume + a plain-text search prompt from the user
and drives the whole pipeline

```
search_listings -> analyze_listing -> personalize_resume -> submit_application
```

making one HTTP call at a time and always waiting for a response before
making the next — no concurrency, no queue, just a sequential loop over
whatever `search_listings` returns (capped by "Max applications to submit
this run" in the UI, default 3, so a broad search prompt doesn't fire off
dozens of real applications unattended).

It holds no business logic of its own — every decision (what skills a
listing wants, how to rewrite the resume, how to fill out the apply form)
happens in the service that owns it. This file is just wiring + a status log.

## Setup

```bash
cd services/frontend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # only needed if a service runs on a non-default port
```

## Running everything

The frontend calls the other four services over HTTP, so they need to be up
first. Each needs its own venv/dependencies per its own README — from the
repo root, in four separate terminals:

```bash
# Terminal 1
cd services/search_listings && source .venv/bin/activate && uvicorn app.main:app --port 8001

# Terminal 2
cd services/analyze_listing && source .venv/bin/activate && uvicorn app.main:app --port 8002

# Terminal 3
cd services/personalize_resume && source .venv/bin/activate && uvicorn app.main:app --port 8003

# Terminal 4
cd services/submit_application && source .venv/bin/activate && uvicorn app.main:app --port 8004
```

Make sure `search_listings` has a saved Handshake session
(`python -m scripts.save_auth`, see its README) and `submit_application` has
a filled-in `.profile/profile.json` (see its README) — both are required for
a run to actually reach a submission, not just fail at those steps.

Then, in a fifth terminal:

```bash
# Terminal 5
cd services/frontend && source .venv/bin/activate && python app.py
```

## Viewing the frontend

Open **http://localhost:8080** in your browser. NiceGUI serves the page
itself — there's no separate build step.

On the page:

1. Paste your resume's full LaTeX source into the **Resume** box.
2. Type what you're looking for in plain text (e.g. "software engineering
   intern, remote, paid, Summer 2026") — this is sent to `search_listings`
   as the `keywords` filter. Optional structured filters (location, pay,
   hours, time of year) are under **Advanced search filters**.
3. Set **Max applications to submit this run** if you don't want the default
   of 3.
4. Click **Find & apply** and watch the **Progress** log and **Results**
   table update as each listing moves through analyze -> personalize ->
   submit.

A failure at any stage for a given listing (e.g. the LLM call errors, or
`submit_application` can't find an apply button) is logged and shown as
`error`/`failed` in that listing's row; the run continues to the next
listing rather than aborting.
