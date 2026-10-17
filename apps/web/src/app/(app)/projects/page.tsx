import type { Metadata } from "next";

import { ProjectsView } from "@/components/work/projects-view";

export const metadata: Metadata = { title: "Projects" };

export default function ProjectsPage() {
  return <ProjectsView />;
}
