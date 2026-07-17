import {
  ArrowSquareOutIcon,
  CheckCircleIcon,
  CircleNotchIcon,
  DownloadSimpleIcon,
  XCircleIcon,
} from "@phosphor-icons/react";

import {
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { ListingResult } from "@/lib/types";
import { downloadBase64, downloadText } from "@/lib/download";

const STATUS_LABEL: Record<ListingResult["status"], string> = {
  analyzing: "Analyzing…",
  personalizing: "Personalizing…",
  done: "Ready",
  error: "Failed",
};

const STATUS_CLASSES: Record<ListingResult["status"], string> = {
  analyzing: "bg-pending-bg text-pending",
  personalizing: "bg-pending-bg text-pending",
  done: "bg-success-bg text-success",
  error: "bg-error-bg text-error",
};

function StatusBadge({ status }: { status: ListingResult["status"] }) {
  const isBusy = status === "analyzing" || status === "personalizing";
  return (
    <Badge className={cn("gap-1", STATUS_CLASSES[status])}>
      {isBusy ? (
        <CircleNotchIcon className="size-3 animate-spin" />
      ) : status === "done" ? (
        <CheckCircleIcon className="size-3" weight="fill" />
      ) : (
        <XCircleIcon className="size-3" weight="fill" />
      )}
      {STATUS_LABEL[status]}
    </Badge>
  );
}

export default function ListingCard({ listing }: { listing: ListingResult }) {
  const tags = [
    ...(listing.values?.required_skills ?? []),
    ...(listing.values?.preferred_skills ?? []),
    ...(listing.values?.keywords ?? []),
  ];

  return (
    <Card>
      <CardHeader>
        <CardTitle className="font-display text-lg font-semibold">
          {listing.title}
        </CardTitle>
        <CardDescription>
          {listing.company}
          {listing.location ? ` · ${listing.location}` : ""}
        </CardDescription>
        <CardAction>
          <StatusBadge status={listing.status} />
        </CardAction>
      </CardHeader>

      <CardContent className="flex flex-col gap-3">
        <a
          href={listing.url}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex w-fit items-center gap-1 text-sm text-accent underline underline-offset-2 hover:text-accent-hover"
        >
          View original listing
          <ArrowSquareOutIcon className="size-3.5" />
        </a>

        {listing.values?.summary ? (
          <p className="text-sm italic text-text-muted">{listing.values.summary}</p>
        ) : null}

        {tags.length > 0 ? (
          <div className="flex flex-wrap gap-1.5">
            {tags.map((tag, i) => (
              <Badge key={`${tag}-${i}`} variant="outline" className="font-normal text-text-muted">
                {tag}
              </Badge>
            ))}
          </div>
        ) : null}

        {listing.status === "error" && listing.error ? (
          <p className="text-sm text-error">{listing.error}</p>
        ) : null}
      </CardContent>

      {listing.status === "done" && listing.resumeFile && listing.resumeLatex ? (
        <CardFooter className="gap-2 border-t bg-transparent pt-4">
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() =>
              downloadBase64(
                listing.filename ?? "resume.pdf",
                listing.resumeFile!,
                "application/pdf"
              )
            }
          >
            <DownloadSimpleIcon />
            Download PDF
          </Button>
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() =>
              downloadText(
                listing.latexFilename ?? "resume.tex",
                listing.resumeLatex!,
                "application/x-tex"
              )
            }
          >
            <DownloadSimpleIcon />
            Download LaTeX
          </Button>
        </CardFooter>
      ) : null}
    </Card>
  );
}
