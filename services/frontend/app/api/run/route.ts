// Orchestrator for the pipeline: search_listings -> analyze_listing ->
// personalize_resume. Calls each service in order, one at a time, always
// awaiting a response before making the next call. Streams newline-delimited
// JSON (RunEvent) so the page can render progress as it happens instead of
// waiting for the whole run to finish.
//
// No submission step: apply forms differ too much listing-to-listing to
// automate reliably, so this route's job ends at handing back a personalized
// resume (LaTeX + PDF) per listing for the user to download and submit
// themselves.

import { config } from "@/lib/config";
import type { ListingResult, ListingValues, RunEvent, RunRequestBody } from "@/lib/types";

export const dynamic = "force-dynamic";

const DEFAULT_MAX_LISTINGS = 3;

function encodeEvent(event: RunEvent): Uint8Array {
  return new TextEncoder().encode(JSON.stringify(event) + "\n");
}

function errorMessage(err: unknown): string {
  return err instanceof Error ? err.message : String(err);
}

async function postJson<T = unknown>(
  url: string,
  body: unknown,
  timeoutMs: number
): Promise<T> {
  let res: Response;
  try {
    res = await fetch(url, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(timeoutMs),
    });
  } catch (err) {
    throw new Error(`Could not reach ${url}: ${errorMessage(err)}`);
  }

  const text = await res.text();
  let json: unknown;
  try {
    json = text ? JSON.parse(text) : undefined;
  } catch {
    json = undefined;
  }

  if (!res.ok) {
    const detail =
      (json as { detail?: string } | undefined)?.detail ?? text ?? res.statusText;
    throw new Error(`${res.status}: ${detail}`);
  }
  return json as T;
}

interface SearchListingsResponse {
  listings: Array<{
    listingId: string;
    title: string;
    company: string;
    location: string;
    url: string;
    descriptionText: string;
  }>;
}

interface AnalyzeListingResponse {
  values: ListingValues;
}

interface PersonalizeResumeResponse {
  resumeFile: string;
  filename: string;
  resumeLatex: string;
  latexFilename: string;
}

export async function POST(request: Request) {
  const body = (await request.json()) as RunRequestBody;

  if (!body.resumeLatex?.trim()) {
    return Response.json({ error: "resumeLatex is required" }, { status: 400 });
  }
  if (!body.keywords?.trim()) {
    return Response.json({ error: "keywords is required" }, { status: 400 });
  }

  const maxListings =
    body.maxListings && body.maxListings > 0 ? body.maxListings : DEFAULT_MAX_LISTINGS;

  const stream = new ReadableStream<Uint8Array>({
    async start(controller) {
      const send = (event: RunEvent) => controller.enqueue(encodeEvent(event));

      try {
        send({ type: "log", message: "Searching listings..." });

        const params: Record<string, string> = { keywords: body.keywords };
        if (body.location) params.location = body.location;
        if (body.pay) params.pay = body.pay;
        if (body.hours) params.hours = body.hours;
        if (body.timeOfYear) params.time_of_year = body.timeOfYear;

        const searchResult = await postJson<SearchListingsResponse>(
          `${config.searchListingsUrl}/search-listings`,
          { params },
          config.requestTimeoutMs
        );
        const listings = searchResult.listings ?? [];
        send({ type: "listings_found", count: listings.length });

        for (const listing of listings.slice(0, maxListings)) {
          const base: Omit<ListingResult, "status"> = {
            listingId: listing.listingId,
            title: listing.title,
            company: listing.company,
            location: listing.location,
            url: listing.url,
          };

          send({ type: "listing", listing: { ...base, status: "analyzing" } });

          try {
            const analysis = await postJson<AnalyzeListingResponse>(
              `${config.analyzeListingUrl}/analyze-listing`,
              {
                listingId: listing.listingId,
                title: listing.title,
                company: listing.company,
                location: listing.location,
                url: listing.url,
                descriptionText: listing.descriptionText,
              },
              config.requestTimeoutMs
            );

            send({ type: "listing", listing: { ...base, status: "personalizing" } });

            const personalized = await postJson<PersonalizeResumeResponse>(
              `${config.personalizeResumeUrl}/personalize-resume`,
              { resumeLatex: body.resumeLatex, values: analysis.values },
              config.requestTimeoutMs
            );

            send({
              type: "listing",
              listing: {
                ...base,
                status: "done",
                values: analysis.values,
                resumeFile: personalized.resumeFile,
                filename: personalized.filename,
                resumeLatex: personalized.resumeLatex,
                latexFilename: personalized.latexFilename,
              },
            });
          } catch (err) {
            send({
              type: "listing",
              listing: { ...base, status: "error", error: errorMessage(err) },
            });
          }
        }

        send({ type: "done" });
      } catch (err) {
        send({ type: "fatal", message: errorMessage(err) });
      } finally {
        controller.close();
      }
    },
  });

  return new Response(stream, {
    headers: {
      "content-type": "application/x-ndjson; charset=utf-8",
      "cache-control": "no-cache",
    },
  });
}
