"use client";

import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import {
  CaretDownIcon,
  CaretUpIcon,
  CircleNotchIcon,
  MagnifyingGlassIcon,
  WarningIcon,
} from "@phosphor-icons/react";

import type { ListingResult, RunEvent, RunRequestBody } from "@/lib/types";
import ListingCard from "@/components/ListingCard";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Card, CardContent } from "@/components/ui/card";

const DEFAULT_MAX_LISTINGS = 3;

export default function Home() {
  const [resumeLatex, setResumeLatex] = useState("");
  const [keywords, setKeywords] = useState("");
  const [location, setLocation] = useState("");
  const [pay, setPay] = useState("");
  const [hours, setHours] = useState("");
  const [timeOfYear, setTimeOfYear] = useState("");
  const [maxListings, setMaxListings] = useState(DEFAULT_MAX_LISTINGS);
  const [showAdvanced, setShowAdvanced] = useState(false);

  const [running, setRunning] = useState(false);
  const [log, setLog] = useState<string[]>([]);
  const [listings, setListings] = useState<ListingResult[]>([]);
  const [fatalError, setFatalError] = useState<string | null>(null);

  const logEndRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    logEndRef.current?.scrollIntoView({ block: "nearest" });
  }, [log]);

  function upsertListing(listing: ListingResult) {
    setListings((prev) => {
      const idx = prev.findIndex((l) => l.listingId === listing.listingId);
      if (idx === -1) return [...prev, listing];
      const next = [...prev];
      next[idx] = listing;
      return next;
    });
  }

  function handleEvent(event: RunEvent) {
    switch (event.type) {
      case "log":
        setLog((prev) => [...prev, event.message]);
        break;
      case "listings_found":
        setLog((prev) => [...prev, `Found ${event.count} listing(s).`]);
        break;
      case "listing":
        upsertListing(event.listing);
        setLog((prev) => [
          ...prev,
          `${event.listing.title} @ ${event.listing.company}: ${event.listing.status}` +
            (event.listing.error ? ` — ${event.listing.error}` : ""),
        ]);
        break;
      case "done":
        setLog((prev) => [...prev, "Done."]);
        toast.success("Run complete.");
        break;
      case "fatal":
        setFatalError(event.message);
        toast.error(event.message);
        break;
    }
  }

  async function runPipeline(e: React.FormEvent) {
    e.preventDefault();

    if (!resumeLatex.trim()) {
      toast.warning("Paste your resume first.");
      return;
    }
    if (!keywords.trim()) {
      toast.warning("Describe what you're looking for first.");
      return;
    }

    setFatalError(null);
    setLog([]);
    setListings([]);
    setRunning(true);

    const requestBody: RunRequestBody = {
      resumeLatex,
      keywords,
      location: location || undefined,
      pay: pay || undefined,
      hours: hours || undefined,
      timeOfYear: timeOfYear || undefined,
      maxListings,
    };

    try {
      const res = await fetch("/api/run", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(requestBody),
      });

      if (!res.ok || !res.body) {
        const data = await res.json().catch(() => null);
        throw new Error(data?.error ?? `Request failed (${res.status})`);
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        let newlineIndex: number;
        while ((newlineIndex = buffer.indexOf("\n")) !== -1) {
          const line = buffer.slice(0, newlineIndex).trim();
          buffer = buffer.slice(newlineIndex + 1);
          if (line) handleEvent(JSON.parse(line) as RunEvent);
        }
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      setFatalError(message);
      toast.error(message);
    } finally {
      setRunning(false);
    }
  }

  return (
    <main className="mx-auto flex w-full max-w-7xl flex-1 flex-col gap-6 px-4 py-6 lg:h-screen lg:min-h-0 lg:overflow-hidden">
      <header className="flex shrink-0 flex-col gap-1">
        <h1 className="font-display text-3xl font-semibold text-text">
          Internship Autopilot
        </h1>
        <p className="text-sm text-text-muted">
          Paste your resume, describe what you&apos;re looking for, and get a
          personalized resume — ready to download as LaTeX or PDF — for each
          matching listing. You submit the application yourself.
        </p>
      </header>

      <div className="grid flex-1 grid-cols-1 gap-6 lg:min-h-0 lg:grid-cols-2">
        <div className="flex flex-col gap-4 lg:min-h-0">
          <Card className="lg:min-h-0 lg:flex-1">
            <CardContent className="flex flex-col gap-4 lg:min-h-0 lg:h-full">
              <form
                onSubmit={runPipeline}
                className="flex flex-col gap-4 lg:min-h-0 lg:h-full"
              >
                <div className="flex flex-col gap-1.5 lg:min-h-0 lg:flex-1">
                  <Label htmlFor="resume">Resume (LaTeX source)</Label>
                  <Textarea
                    id="resume"
                    value={resumeLatex}
                    onChange={(e) => setResumeLatex(e.target.value)}
                    placeholder={"\\documentclass[letterpaper,11pt]{article}\n...\n\\end{document}"}
                    className="field-sizing-fixed resize-none font-mono lg:h-full lg:min-h-0 lg:flex-1"
                  />
                </div>

                <div className="flex shrink-0 flex-col gap-1.5">
                  <Label htmlFor="keywords">
                    What kind of internship are you looking for?
                  </Label>
                  <Input
                    id="keywords"
                    value={keywords}
                    onChange={(e) => setKeywords(e.target.value)}
                    placeholder="e.g. software engineering intern, remote, paid, Summer 2026"
                  />
                </div>

                <div className="shrink-0">
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    onClick={() => setShowAdvanced((v) => !v)}
                    className="px-0 text-accent hover:bg-transparent hover:text-accent-hover"
                  >
                    {showAdvanced ? <CaretUpIcon /> : <CaretDownIcon />}
                    {showAdvanced ? "Hide" : "Show"} advanced search filters
                  </Button>
                  {showAdvanced ? (
                    <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2">
                      <Input
                        value={location}
                        onChange={(e) => setLocation(e.target.value)}
                        placeholder="Location"
                      />
                      <Input
                        value={pay}
                        onChange={(e) => setPay(e.target.value)}
                        placeholder="Pay"
                      />
                      <Input
                        value={hours}
                        onChange={(e) => setHours(e.target.value)}
                        placeholder="Hours"
                      />
                      <Input
                        value={timeOfYear}
                        onChange={(e) => setTimeOfYear(e.target.value)}
                        placeholder="Time of year"
                      />
                    </div>
                  ) : null}
                </div>

                <div className="flex shrink-0 flex-col gap-1.5 sm:w-64">
                  <Label htmlFor="max-listings">Max listings to process this run</Label>
                  <Input
                    id="max-listings"
                    type="number"
                    min={1}
                    max={25}
                    value={maxListings}
                    onChange={(e) =>
                      setMaxListings(Number(e.target.value) || DEFAULT_MAX_LISTINGS)
                    }
                  />
                </div>

                <Button
                  type="submit"
                  disabled={running}
                  className="w-fit shrink-0"
                >
                  {running ? (
                    <CircleNotchIcon className="animate-spin" />
                  ) : (
                    <MagnifyingGlassIcon />
                  )}
                  {running ? "Running…" : "Find listings"}
                </Button>
              </form>
            </CardContent>
          </Card>
        </div>

        <div className="flex flex-col gap-4 lg:min-h-0">
          {fatalError ? (
            <Card className="shrink-0 border-error bg-error-bg">
              <CardContent className="flex items-start gap-2 text-sm text-error">
                <WarningIcon className="mt-0.5 size-4 shrink-0" weight="fill" />
                {fatalError}
              </CardContent>
            </Card>
          ) : null}

          {log.length > 0 ? (
            <section className="flex shrink-0 flex-col gap-2">
              <h2 className="font-display text-lg font-semibold text-text">
                Progress
              </h2>
              <div className="max-h-40 overflow-y-auto rounded-lg border border-border bg-surface p-4 font-mono text-sm text-text-muted">
                {log.map((line, i) => (
                  <div key={i}>{line}</div>
                ))}
                <div ref={logEndRef} />
              </div>
            </section>
          ) : null}

          <section className="flex flex-1 flex-col gap-2 lg:min-h-0">
            <h2 className="font-display text-lg font-semibold text-text">
              Results
            </h2>
            {listings.length > 0 ? (
              <ul className="flex flex-1 flex-col gap-4 overflow-y-auto pr-1 lg:min-h-0">
                {listings.map((listing) => (
                  <li key={listing.listingId}>
                    <ListingCard listing={listing} />
                  </li>
                ))}
              </ul>
            ) : (
              <div className="flex flex-1 items-center justify-center rounded-lg border border-dashed border-border p-8 text-center text-sm text-text-muted lg:min-h-0">
                Results will appear here once a run starts.
              </div>
            )}
          </section>
        </div>
      </div>
    </main>
  );
}
