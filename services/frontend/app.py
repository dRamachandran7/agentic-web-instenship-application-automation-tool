"""Frontend + orchestrator for the internship application pipeline.

A single NiceGUI page: the user pastes their resume (LaTeX source) and types
a plain-text search prompt, then the pipeline runs

    search_listings -> analyze_listing -> personalize_resume -> submit_application

one call at a time, always waiting for a response before making the next
call. This file *is* the orchestrator the other services' READMEs refer to —
it holds no business logic of its own, just wiring and status display.
"""

from __future__ import annotations

import httpx
from nicegui import ui

from config import settings

DEFAULT_MAX_LISTINGS = 3


def _build_params(keywords: str, location: str, pay: str, hours: str, time_of_year: str) -> dict:
    params: dict[str, str] = {"keywords": keywords}
    if location:
        params["location"] = location
    if pay:
        params["pay"] = pay
    if hours:
        params["hours"] = hours
    if time_of_year:
        params["time_of_year"] = time_of_year
    return params


@ui.page("/")
def index() -> None:
    with ui.column().classes("w-full max-w-3xl mx-auto gap-4 p-4"):
        ui.label("Internship Application Automation").classes("text-2xl font-bold")
        ui.label(
            "Paste your resume and describe what you're looking for. This runs "
            "search_listings -> analyze_listing -> personalize_resume -> "
            "submit_application in order, waiting for each step to finish "
            "before starting the next."
        ).classes("text-sm text-gray-500")

        resume_input = (
            ui.textarea(
                label="Resume (LaTeX source)",
                placeholder=r"\documentclass[letterpaper,11pt]{article} ... \end{document}",
            )
            .classes("w-full")
            .props("outlined rows=14")
        )

        prompt_input = ui.input(
            label="What kind of internship are you looking for?",
            placeholder="e.g. software engineering intern, remote, paid, Summer 2026",
        ).classes("w-full")

        with ui.expansion("Advanced search filters (optional)").classes("w-full"):
            with ui.row().classes("w-full"):
                location_input = ui.input(label="Location").classes("flex-1")
                pay_input = ui.input(label="Pay").classes("flex-1")
            with ui.row().classes("w-full"):
                hours_input = ui.input(label="Hours").classes("flex-1")
                time_of_year_input = ui.input(label="Time of year").classes("flex-1")

        max_listings_input = ui.number(
            label="Max applications to submit this run",
            value=DEFAULT_MAX_LISTINGS,
            min=1,
            max=25,
        )

        run_button = ui.button("Find & apply")

        ui.label("Progress").classes("text-lg font-semibold mt-2")
        log = ui.log(max_lines=500).classes("w-full h-64")

        ui.label("Results").classes("text-lg font-semibold mt-2")
        results_table = ui.table(
            columns=[
                {"name": "title", "label": "Listing", "field": "title"},
                {"name": "company", "label": "Company", "field": "company"},
                {"name": "status", "label": "Status", "field": "status"},
                {"name": "detail", "label": "Detail", "field": "detail"},
            ],
            rows=[],
            row_key="listingId",
        ).classes("w-full")

        async def run_pipeline() -> None:
            resume_latex = resume_input.value.strip() if resume_input.value else ""
            keywords = prompt_input.value.strip() if prompt_input.value else ""
            if not resume_latex:
                ui.notify("Paste your resume first.", type="warning")
                return
            if not keywords:
                ui.notify("Describe what you're looking for first.", type="warning")
                return

            run_button.disable()
            log.clear()
            results_table.rows.clear()
            results_table.update()

            params = _build_params(
                keywords,
                location_input.value,
                pay_input.value,
                hours_input.value,
                time_of_year_input.value,
            )
            max_listings = int(max_listings_input.value or DEFAULT_MAX_LISTINGS)

            try:
                async with httpx.AsyncClient(timeout=settings.request_timeout_s) as client:
                    log.push("Searching listings...")
                    resp = await client.post(
                        f"{settings.search_listings_url}/search-listings", json={"params": params}
                    )
                    resp.raise_for_status()
                    listings = resp.json()["listings"]
                    log.push(f"Found {len(listings)} listing(s).")

                    if not listings:
                        ui.notify("No listings found.", type="info")
                        return

                    for listing in listings[:max_listings]:
                        await _apply_to_listing(client, listing, resume_latex, log, results_table)
            except httpx.HTTPStatusError as exc:
                log.push(f"Search failed: {exc.response.status_code} {exc.response.text[:300]}")
                ui.notify("Search failed — see log.", type="negative")
            except httpx.HTTPError as exc:
                log.push(f"Search failed: {exc}")
                ui.notify("Search failed — see log.", type="negative")
            finally:
                run_button.enable()

        run_button.on_click(run_pipeline)


async def _apply_to_listing(
    client: httpx.AsyncClient, listing: dict, resume_latex: str, log, results_table
) -> None:
    title, company = listing["title"], listing["company"]
    row = {
        "listingId": listing["listingId"],
        "title": title,
        "company": company,
        "status": "in progress",
        "detail": "",
    }
    results_table.rows.append(row)
    results_table.update()

    try:
        log.push(f"Analyzing: {title} @ {company}")
        resp = await client.post(
            f"{settings.analyze_listing_url}/analyze-listing",
            json={
                "listingId": listing["listingId"],
                "title": title,
                "company": company,
                "location": listing.get("location", ""),
                "url": listing["url"],
                "descriptionText": listing["descriptionText"],
            },
        )
        resp.raise_for_status()
        values = resp.json()["values"]

        log.push(f"Personalizing resume for: {title}")
        resp = await client.post(
            f"{settings.personalize_resume_url}/personalize-resume",
            json={"resumeLatex": resume_latex, "values": values},
        )
        resp.raise_for_status()
        personalized = resp.json()

        log.push(f"Submitting application: {title}")
        resp = await client.post(
            f"{settings.submit_application_url}/submit-application",
            json={
                "listingId": listing["listingId"],
                "url": listing["url"],
                "resumeFile": personalized["resumeFile"],
                "resumeFilename": personalized.get("filename", "resume.pdf"),
            },
        )
        resp.raise_for_status()
        result = resp.json()

        row["status"] = result["status"]
        row["detail"] = result.get("confirmationId") or result.get("error") or ""
        log.push(f"-> {result['status']} ({row['detail'] or 'no detail'})")
    except httpx.HTTPStatusError as exc:
        row["status"] = "error"
        row["detail"] = f"{exc.response.status_code}: {exc.response.text[:200]}"
        log.push(f"-> error on {title}: {row['detail']}")
    except httpx.HTTPError as exc:
        row["status"] = "error"
        row["detail"] = str(exc)
        log.push(f"-> error on {title}: {row['detail']}")
    finally:
        results_table.update()


if __name__ in {"__main__", "__mp_main__"}:
    ui.run(title="Internship Autopilot", port=settings.port)
