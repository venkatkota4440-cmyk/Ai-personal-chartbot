import type { Metadata } from "next";

import { UpcomingFeature } from "@/components/upcoming-feature";

export const metadata: Metadata = { title: "Files" };

export default function FilesPage() {
  return (
    <UpcomingFeature
      title="Files"
      description="Upload documents and get summaries."
      milestone="M6"
      plannedCapabilities={[
        "Upload supported files with type and size checks",
        "Summaries that cite the source document",
        "Document text is treated as data, never as instructions",
      ]}
    />
  );
}
