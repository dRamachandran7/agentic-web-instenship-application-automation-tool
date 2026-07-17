// Shapes shared between the /api/run route handler (server) and the page
// (client) that streams and renders its output.

export type ListingStatus = "analyzing" | "personalizing" | "done" | "error";

export interface ListingValues {
  required_skills: string[];
  preferred_skills: string[];
  keywords: string[];
  values: string[];
  summary: string;
}

export interface ListingResult {
  listingId: string;
  title: string;
  company: string;
  location?: string;
  url: string;
  status: ListingStatus;
  error?: string;
  values?: ListingValues;
  // Populated once personalize_resume returns, base64-encoded PDF bytes.
  resumeFile?: string;
  filename?: string;
  resumeLatex?: string;
  latexFilename?: string;
}

export type RunEvent =
  | { type: "log"; message: string }
  | { type: "listings_found"; count: number }
  | { type: "listing"; listing: ListingResult }
  | { type: "done" }
  | { type: "fatal"; message: string };

export interface RunRequestBody {
  resumeLatex: string;
  keywords: string;
  location?: string;
  pay?: string;
  hours?: string;
  timeOfYear?: string;
  maxListings?: number;
}
