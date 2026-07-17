// Server-only: base URLs for the three pipeline services this frontend
// orchestrates. Never imported from a Client Component.
export const config = {
  searchListingsUrl: process.env.SEARCH_LISTINGS_URL ?? "http://localhost:8001",
  analyzeListingUrl: process.env.ANALYZE_LISTING_URL ?? "http://localhost:8002",
  personalizeResumeUrl: process.env.PERSONALIZE_RESUME_URL ?? "http://localhost:8003",
  requestTimeoutMs: Number(process.env.REQUEST_TIMEOUT_MS ?? 120_000),
};
