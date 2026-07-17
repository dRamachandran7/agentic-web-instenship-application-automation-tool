# frontend

A [Next.js](https://nextjs.org) app that is both the UI and the orchestrator
for the pipeline

```
search_listings -> analyze_listing -> personalize_resume
```

The user pastes their resume (LaTeX source) and a plain-text search prompt.
`app/api/run/route.ts` calls the three backend services in order — one call
at a time, always waiting for a response before making the next — and
streams progress back to the page as newline-delimited JSON so results show
up incrementally instead of after the whole run finishes.

There is no automated submission step. Apply forms differ too much
listing-to-listing (different fields, some redirect to a different ATS
entirely) to automate reliably, so the app's job ends at handing back, per
listing, a personalized resume as both a **PDF download** and a **LaTeX
download** — the user reviews and submits the application themselves.

## Setup

```bash
cd services/frontend
npm install
cp .env.local.example .env.local   # only needed if a service runs on a non-default port
```

## Running everything

The frontend calls the other three services over HTTP, so they need to be up
first. Each needs its own venv/dependencies per its own README — from the
repo root, in three separate terminals:

```bash
# Terminal 1
cd services/search_listings && source .venv/bin/activate && uvicorn app.main:app --port 8001

# Terminal 2
cd services/analyze_listing && source .venv/bin/activate && uvicorn app.main:app --port 8002

# Terminal 3
cd services/personalize_resume && source .venv/bin/activate && uvicorn app.main:app --port 8003
```

Make sure `search_listings` has a saved Handshake session
(`python -m scripts.save_auth`, see its README) — otherwise the run will
fail at the first step.

Then, in a fourth terminal:

```bash
# Terminal 4
cd services/frontend && npm run dev
```

## Viewing the frontend

Open **http://localhost:3000** in your browser.

On the page:

1. Paste your resume's full LaTeX source into the **Resume** box.
2. Type what you're looking for in plain text (e.g. "software engineering
   intern, remote, paid, Summer 2026") — sent to `search_listings` as the
   `keywords` filter. Optional structured filters (location, pay, hours,
   time of year) are under **Show advanced search filters**.
3. Set **Max listings to process this run** if you don't want the default
   of 3 (keeps a broad search prompt from triggering a large batch of LLM
   calls and LaTeX compiles unattended).
4. Click **Find listings** and watch the **Progress** log and **Results**
   cards update as each listing moves through analyze -> personalize.
5. For each finished listing, click **Download PDF** or **Download LaTeX**
   to get the personalized resume, then apply on the listing's original page
   (linked on each card) yourself.

A failure at any stage for a given listing (e.g. the LLM call errors, or the
LaTeX the model produced doesn't compile) is shown as `Failed` on that
listing's card with the error message; the run continues to the next
listing rather than aborting.

## Project structure

- `app/page.tsx` — the whole UI: form, progress log, results list. A Client
  Component (`"use client"`) since it's one continuously-interactive tool,
  not worth splitting into server/client halves.
- `app/api/run/route.ts` — the orchestrator. A Route Handler that streams an
  NDJSON `ReadableStream` of `RunEvent`s (see `lib/types.ts`).
- `components/ListingCard.tsx` — one listing's result: status, extracted
  skills, and the two download buttons.
- `components/ui/*` — [shadcn/ui](https://ui.shadcn.com) primitives
  (Button, Input, Textarea, Label, Card, Badge, Sonner's `Toaster`).
- `lib/config.ts` — service base URLs, read from env vars server-side only.
- `lib/download.ts` — client-only Blob-based download helpers (used instead
  of raw `data:` URIs so PDF-sized payloads don't hit a browser's URL length
  limit).

## Design system

- **Components**: [shadcn/ui](https://ui.shadcn.com) (`components.json`,
  `components/ui/`) — semantic tokens (`--primary`, `--background`,
  `--border`, ...) are remapped in `app/globals.css` onto the warm palette
  below, so shadcn's own components inherit the theme instead of its default
  neutral-grey scale. Add more components with `npx shadcn@latest add <name>`.
- **Icons**: [`@phosphor-icons/react`](https://phosphoricons.com) (import
  the `*Icon`-suffixed names, e.g. `CheckCircleIcon` — the un-suffixed
  aliases are deprecated in this version).
- **Toasts**: [`sonner`](https://sonner.emilkowal.ski) via
  `components/ui/sonner.tsx`'s `<Toaster />` (mounted in `app/layout.tsx`),
  called with `toast.success()` / `toast.warning()` / `toast.error()`.
- **Palette**: "Warm & Grounded" — terracotta accent (`#c0603a`) on warm
  cream/charcoal neutrals, flat (no shadows/gradients), Fraunces (display) +
  Inter (body/UI). Chosen deliberately over generic SaaS blue — see
  `app/globals.css` for the full token list.
- **No dark mode**: the warm/light palette is a deliberate, single committed
  look for this internal tool, not an oversight. `next-themes` was
  intentionally *not* installed; `sonner.tsx` hardcodes `theme="light"`
  rather than reading a theme that doesn't exist.

## Notes

- This project was scaffolded on Next.js 16, which has real breaking changes
  from older training data — see `AGENTS.md` before making framework-level
  changes (route handlers, caching, env vars, etc.).
