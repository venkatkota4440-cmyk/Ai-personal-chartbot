import type { Metadata } from "next";

import { TasksView } from "@/components/work/tasks-view";

export const metadata: Metadata = { title: "Tasks" };

export default function TasksPage() {
  return <TasksView />;
}
