"""Selector diagnostic for the Handshake scraper.

Opens a listing using your saved session (the same way the scraper does), then
reports:
  1. Which of the current selectors in handshake.py actually match, with a text
     preview — so you can see exactly what's missing or truncated.
  2. An inventory of the real `data-hook` / `data-testid` / `id` attributes and
     headings on the page — the raw material for picking better selectors.
  3. The largest text blocks on the page — the biggest one is almost always the
     full job description, so you can grab its container selector.

It also dumps the rendered HTML and a screenshot to `debug/` for offline
inspection, and (with --pause) drops into the Playwright Inspector so you can
hover elements and copy selectors interactively.

Usage (from services/search_listings/, with your venv active):
    python -m scripts.inspect_listing                 # search + click first result
    python -m scripts.inspect_listing --url <listing-url>
    python -m scripts.inspect_listing --keywords "software intern" --pause
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import settings  # noqa: E402
from app.scraper import handshake as hs  # noqa: E402

DEBUG_DIR = Path(__file__).resolve().parents[1] / "debug"

# Groups of (label, selector-list) pulled straight from the scraper so this
# report reflects exactly what the service uses.
FIELD_GROUPS = [
    ("title", hs.DETAIL_TITLE_SELECTORS),
    ("company", hs.DETAIL_COMPANY_SELECTORS),
    ("location", hs.DETAIL_LOCATION_SELECTORS),
    ("description", hs.DETAIL_DESCRIPTION_SELECTORS),
]

# JS that inventories attributes useful for building stable selectors.
INVENTORY_JS = """
() => {
  const trim = s => (s || '').replace(/\\s+/g, ' ').trim();
  const collect = attr => {
    const out = {};
    for (const el of document.querySelectorAll('[' + attr + ']')) {
      const v = el.getAttribute(attr);
      if (!v) continue;
      const txt = trim(el.innerText);
      if (!(v in out)) out[v] = { count: 0, len: 0, preview: '' };
      out[v].count += 1;
      if (txt.length > out[v].len) { out[v].len = txt.length; out[v].preview = txt.slice(0, 80); }
    }
    return out;
  };
  const headings = [];
  for (const h of document.querySelectorAll('h1, h2, h3')) {
    const t = trim(h.innerText);
    if (t) headings.push(h.tagName.toLowerCase() + ': ' + t.slice(0, 80));
  }
  // Largest text containers -> likely the description body.
  const blocks = [];
  for (const el of document.querySelectorAll('div, section, article, main, li')) {
    const len = trim(el.innerText).length;
    if (len < 200) continue;
    const sel =
      el.getAttribute('data-hook') ? '[data-hook="' + el.getAttribute('data-hook') + '"]' :
      el.getAttribute('data-testid') ? '[data-testid="' + el.getAttribute('data-testid') + '"]' :
      el.id ? '#' + el.id :
      el.tagName.toLowerCase() + (el.className && typeof el.className === 'string'
        ? '.' + el.className.trim().split(/\\s+/).slice(0, 2).join('.') : '');
    blocks.push({ len, sel });
  }
  blocks.sort((a, b) => b.len - a.len);
  // Employer links -> the company name/selector.
  const employerLinks = [];
  for (const a of document.querySelectorAll('a[href*="/e/"]')) {
    employerLinks.push({ href: a.getAttribute('href'), text: trim(a.innerText).slice(0, 60) });
  }
  // Text under key headings -> where location/company detail lives.
  const sections = {};
  for (const h of document.querySelectorAll('h1, h2, h3, h4')) {
    const label = trim(h.innerText);
    if (!['At a glance', 'About the employer'].includes(label)) continue;
    const box = h.closest('section') || h.parentElement;
    sections[label] = trim(box ? box.innerText : '').slice(0, 300);
  }
  return {
    dataHook: collect('data-hook'),
    dataTestid: collect('data-testid'),
    ids: collect('id'),
    headings,
    blocks: blocks.slice(0, 8),
    employerLinks: employerLinks.slice(0, 8),
    sections,
  };
}
"""


def _load_listing_page(context, page, args):
    """Load a listing and return the page that actually holds the detail (a
    click may open it in a new tab)."""
    if args.url:
        page.goto(args.url, wait_until="networkidle")
        return page
    # Mirror the scraper: search, then click the first result so we inspect
    # whatever the click actually produces (a detail page OR a preview panel).
    url = f"{settings.handshake_base_url.rstrip('/')}{hs.JOB_SEARCH_PATH}"
    if args.keywords:
        url += f"?{hs.QUERY_PARAM_KEYWORDS}={args.keywords.replace(' ', '+')}"
    page.goto(url, wait_until="networkidle")
    link = page.query_selector(hs.RESULT_LINK_SELECTOR)
    if link is None:
        print("!! No result links matched RESULT_LINK_SELECTOR on the search page.")
        print("   Fix RESULT_LINK_SELECTOR first, or pass --url <listing-url>.")
        return page

    before = set(context.pages)
    link.click()
    page.wait_for_load_state("networkidle")

    # Did the click open a new tab, or render inline on the same page?
    new_pages = [p for p in context.pages if p not in before]
    print("\n=== Navigation after click ===")
    print(f"  Open tabs: {[p.url for p in context.pages]}")
    if new_pages:
        detail = new_pages[-1]
        detail.wait_for_load_state("networkidle")
        print(f"  Click opened a NEW tab -> inspecting {detail.url}")
        print("  (The scraper navigates directly to /jobs/<id>; that matches this.)")
        return detail
    print(f"  Rendered inline on same page -> {page.url}")
    print("  (No separate URL — scraper must click, not navigate. Flag this.)")
    return page


def _report_current_selectors(page) -> None:
    print("\n=== 1. Current selectors (from handshake.py) ===")
    for label, selectors in FIELD_GROUPS:
        print(f"\n[{label}]")
        any_hit = False
        for sel in selectors:
            els = page.query_selector_all(sel)
            if not els:
                print(f"  MISS  {sel}")
                continue
            any_hit = True
            text = (els[0].inner_text() or "").strip().replace("\n", " ")
            print(f"  HIT   {sel}  ({len(els)} match, {len(text)} chars)")
            print(f'        -> "{text[:100]}"')
        if not any_hit:
            print("  (nothing matched — needs a new selector)")


def _report_inventory(page) -> None:
    inv = page.evaluate(INVENTORY_JS)

    def dump(title, mapping):
        print(f"\n--- {title} ---")
        if not mapping:
            print("  (none)")
            return
        for key, info in sorted(mapping.items(), key=lambda kv: -kv[1]["len"])[:25]:
            print(f'  {key!r}  (x{info["count"]}, {info["len"]} chars)  "{info["preview"]}"')

    print("\n=== 2. Attribute inventory (candidates for selectors) ===")
    dump("data-hook", inv["dataHook"])
    dump("data-testid", inv["dataTestid"])
    dump("id", inv["ids"])

    print("\n--- headings (h1/h2/h3) ---")
    for h in inv["headings"][:15]:
        print(f"  {h}")

    print("\n=== 3. Largest text blocks (likely the description body) ===")
    for b in inv["blocks"]:
        print(f'  {b["len"]:>6} chars  ->  {b["sel"]}')

    print("\n=== 4. Employer links (company name/selector) ===")
    for link in inv["employerLinks"] or []:
        print(f'  {link["href"]}  ->  "{link["text"]}"')
    if not inv["employerLinks"]:
        print("  (none — company must come from text, not a link)")

    print("\n=== 5. Key section text (where location lives) ===")
    for label, text in (inv["sections"] or {}).items():
        print(f'  [{label}]\n    {text!r}')
    if not inv["sections"]:
        print("  (no 'At a glance' / 'About the employer' headings found)")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", help="A specific listing URL to inspect.")
    ap.add_argument("--keywords", default="intern", help="Search keywords when no --url.")
    ap.add_argument("--pause", action="store_true", help="Open Playwright Inspector.")
    args = ap.parse_args()

    state = settings.storage_state_path
    if not state.exists():
        sys.exit(f"No saved session at {state}. Run `python -m scripts.save_auth` first.")

    DEBUG_DIR.mkdir(exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(storage_state=str(state))
        page = context.new_page()

        page = _load_listing_page(context, page, args)
        print(f"\nInspecting URL: {page.url}")

        (DEBUG_DIR / "listing.html").write_text(page.content(), encoding="utf-8")
        page.screenshot(path=str(DEBUG_DIR / "listing.png"), full_page=True)

        _report_current_selectors(page)
        _report_inventory(page)

        print(f"\nSaved rendered HTML -> {DEBUG_DIR / 'listing.html'}")
        print(f"Saved screenshot    -> {DEBUG_DIR / 'listing.png'}")

        if args.pause:
            print("\nOpening Playwright Inspector — hover elements to copy selectors.")
            page.pause()

        browser.close()


if __name__ == "__main__":
    main()
