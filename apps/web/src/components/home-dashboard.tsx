"use client";

import type { Approval, Project, Run, Task } from "@shared/types";
import { ChevronRight, FolderKanban, ListChecks, ShieldCheck, Workflow } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

import { ListSection, Row } from "@/components/ui/list";
import { StatusChip } from "@/components/ui/status-chip";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/states";
import { api, ApiError } from "@/lib/api";
import { useCurrentUser } from "@/lib/session";
import { greetingFor } from "@/lib/time";

interface Summary {
  tasks: Task[];
  projects: Project[];
  approvals: Approval[];
  runs: Run[];
}

type LoadState = { status: "loading" } | { status: "ready"; data: Summary } | { status: "error"; error: ApiError };

function isDueSoon(task: Task): boolean {
  if (task.status === "done") return false;
  if (task.priority === "urgent") return true;
  if (!task.due_at) return false;
  return new Date(task.due_at).toDateString() <= new Date().toDateString();
}

export function HomeDashboard() {
  const user = useCurrentUser();
  // Safe during render: this component only mounts on the client, after the session resolves.
  const greeting = greetingFor(new Date(), user.timezone);
  // The local part of an email can be one long unbroken word, so cap it for the greeting.
  const local = user.email.split("@")[0] ?? "there";
  const name = local.length > 18 ? `${local.slice(0, 18)}…` : local;

  const [load, setLoad] = useState<LoadState>({ status: "loading" });
  const [version, setVersion] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    const options = { signal: controller.signal };
    Promise.all([
      api<Task[]>("/api/tasks", options),
      api<Project[]>("/api/projects", options),
      api<Approval[]>("/api/approvals?status=pending", options),
      api<Run[]>("/api/automations", options).then(async (automations) => {
        const lists = await Promise.all(
          (automations as unknown as { id: string }[])
            .slice(0, 5)
            .map((a) => api<Run[]>(`/api/automations/${a.id}/runs`, options).catch(() => [])),
        );
        return lists
          .flat()
          .sort((a, b) => b.created_at.localeCompare(a.created_at))
          .slice(0, 4);
      }),
    ])
      .then(([tasks, projects, approvals, runs]) => setLoad({ status: "ready", data: { tasks, projects, approvals, runs } }))
      .catch((e: unknown) => {
        if (!controller.signal.aborted) setLoad({ status: "error", error: e as ApiError });
      });
    return () => controller.abort();
  }, [version]);

  return (
    <>
      <header className="mb-6 animate-appear">
        <p className="text-subhead font-medium text-blue">Today</p>
        <h1 className="mt-0.5 text-largetitle font-bold tracking-tight text-label [overflow-wrap:anywhere]">
          {greeting}, {name}
        </h1>
      </header>

      {load.status === "loading" && <LoadingState label="Loading your day…" />}
      {load.status === "error" && <ErrorState error={load.error} onRetry={() => setVersion((n) => n + 1)} />}

      {load.status === "ready" && (
        <div className="flex flex-col gap-5">
          {load.data.approvals.length > 0 && (
            <ListSection header="Waiting for you">
              {load.data.approvals.map((approval) => (
                <Row
                  key={approval.id}
                  href="/approvals"
                  leading={<ShieldCheck aria-hidden="true" className="size-5 flex-none text-orange" />}
                  title={approval.action_summary}
                  subtitle={approval.target}
                />
              ))}
            </ListSection>
          )}

          <ListSection header="Today's priorities" footer={<Link href="/tasks">See all tasks ›</Link>}>
            {load.data.tasks.filter(isDueSoon).length === 0 ? (
              <EmptyState icon={ListChecks} title="Nothing urgent" description="No tasks due today or marked urgent." />
            ) : (
              load.data.tasks
                .filter(isDueSoon)
                .slice(0, 5)
                .map((task) => (
                  <Row
                    key={task.id}
                    href="/tasks"
                    title={task.title}
                    subtitle={task.due_at ? new Date(task.due_at).toLocaleString() : task.priority}
                  />
                ))
            )}
          </ListSection>

          <ListSection header="Active projects">
            {load.data.projects.filter((p) => p.status === "active").length === 0 ? (
              <EmptyState icon={FolderKanban} title="No active projects" description="Create one from Projects." />
            ) : (
              load.data.projects
                .filter((p) => p.status === "active")
                .slice(0, 4)
                .map((project) => (
                  <Row
                    key={project.id}
                    href="/projects"
                    title={project.name}
                    subtitle={`${project.task_open} open · ${project.task_done}/${project.task_total} done`}
                  />
                ))
            )}
          </ListSection>

          <ListSection header="Recent runs" footer={<Link href="/automations">See automations ›</Link>}>
            {load.data.runs.length === 0 ? (
              <EmptyState icon={Workflow} title="No runs yet" description="Open an automation and press Run now." />
            ) : (
              load.data.runs.map((run) => (
                <Row
                  key={run.id}
                  href="/automations"
                  title={run.output_summary ?? `Run ${run.trigger}`}
                  subtitle={new Date(run.created_at).toLocaleString()}
                  trailing={<StatusChip status={run.status} />}
                />
              ))
            )}
          </ListSection>

          <Link
            href="/chat"
            className="flex min-h-11 items-center justify-between rounded-card bg-surface px-4 py-3 text-body text-blue"
          >
            Ask your assistant something
            <ChevronRight aria-hidden="true" className="size-4" />
          </Link>
        </div>
      )}
    </>
  );
}
