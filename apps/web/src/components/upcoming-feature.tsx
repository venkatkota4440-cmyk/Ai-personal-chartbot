import { Construction } from "lucide-react";

import { PageHeader } from "@/components/page-header";
import { ListSection, Row } from "@/components/ui/list";
import { EmptyState } from "@/components/ui/states";

/**
 * Honest placeholder for a section scheduled for a later milestone.
 * It says plainly that the feature is not built yet instead of showing fake data.
 */
export function UpcomingFeature({
  title,
  description,
  milestone,
  plannedCapabilities,
}: {
  title: string;
  description: string;
  milestone: string;
  plannedCapabilities: string[];
}) {
  return (
    <>
      <PageHeader title={title} description={description} />
      <div className="rounded-card bg-surface">
        <EmptyState
          icon={Construction}
          title={`Not available yet — planned for ${milestone}`}
          description="Nothing here is simulated. This section will appear when that milestone ships."
        />
      </div>
      <ListSection header="What this will do" className="mt-5">
        {plannedCapabilities.map((capability) => (
          <Row key={capability} title={<span className="whitespace-normal">{capability}</span>} />
        ))}
      </ListSection>
    </>
  );
}
