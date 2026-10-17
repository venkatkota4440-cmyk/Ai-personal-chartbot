"use client";

import type { Project } from "@shared/types";
import { FolderKanban, Plus } from "lucide-react";
import { useEffect, useState, type FormEvent } from "react";

import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { TextField } from "@/components/ui/field";
import { ListSection, Row } from "@/components/ui/list";
import { EmptyState, ErrorState, LoadingState, Notice } from "@/components/ui/states";
import { api, ApiError } from "@/lib/api";
import { toApiError } from "@/lib/errors";

type LoadState = { status: "loading" } | { status: "ready"; projects: Project[] } | { status: "error"; error: ApiError };

function ProgressRing({ done, total }: { done: number; total: number }) {
  const fraction = total === 0 ? 0 : done / total;
  const size = 34;
  const radius = 14;
  const circumference = 2 * Math.PI * radius;
  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} aria-hidden="true" className="flex-none">
      <circle cx={size / 2} cy={size / 2} r={radius} fill="none" stroke="var(--color-fill)" strokeWidth="3" />
      <circle
        cx={size / 2}
        cy={size / 2}
        r={radius}
        fill="none"
        stroke="var(--color-blue)"
        strokeWidth="3"
        strokeLinecap="round"
        strokeDasharray={`${circumference * fraction} ${circumference}`}
        transform={`rotate(-90 ${size / 2} ${size / 2})`}
      />
      <text
        x="50%"
        y="50%"
        dominantBaseline="central"
        textAnchor="middle"
        fontSize="10"
        fontWeight="600"
        fill="var(--color-label-2)"
      >
        {total === 0 ? "–" : `${Math.round(fraction * 100)}`}
      </text>
    </svg>
  );
}

export function ProjectsView() {
  const [load, setLoad] = useState<LoadState>({ status: "loading" });
  const [version, setVersion] = useState(0);
  const [adding, setAdding] = useState(false);
  const [name, setName] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    api<Project[]>("/api/projects", { signal: controller.signal })
      .then((projects) => setLoad({ status: "ready", projects }))
      .catch((e: unknown) => {
        if (!controller.signal.aborted) setLoad({ status: "error", error: toApiError(e) });
      });
    return () => controller.abort();
  }, [version]);

  const create = async (event: FormEvent) => {
    event.preventDefault();
    if (!name.trim()) return;
    setPending(true);
    setError(null);
    try {
      const created = await api<Project>("/api/projects", { method: "POST", body: { name: name.trim() } });
      setLoad((c) =>
        c.status === "ready"
          ? { status: "ready", projects: [{ ...created, task_total: 0, task_done: 0, task_open: 0 }, ...c.projects] }
          : c,
      );
      setName("");
      setAdding(false);
    } catch (e) {
      setError(toApiError(e).message);
    } finally {
      setPending(false);
    }
  };

  return (
    <>
      <PageHeader
        title="Projects"
        description="Group your work. ScamShield AI is seeded with synthetic milestones."
        actions={
          <Button variant="tinted" onClick={() => setAdding((v) => !v)} aria-expanded={adding}>
            <Plus aria-hidden="true" className="size-4" />
            New project
          </Button>
        }
      />

      {adding && (
        <form onSubmit={create} className="mb-4 flex flex-col gap-3 rounded-card bg-surface p-4">
          <TextField label="Project name" value={name} maxLength={200} onChange={(e) => setName(e.target.value)} autoFocus />
          {error && <Notice tone="error">{error}</Notice>}
          <div className="flex gap-2">
            <Button type="submit" loading={pending} disabled={!name.trim()}>
              Create
            </Button>
            <Button type="button" variant="plain" onClick={() => setAdding(false)}>
              Cancel
            </Button>
          </div>
        </form>
      )}

      {load.status === "loading" && <LoadingState label="Loading projects…" />}
      {load.status === "error" && <ErrorState error={load.error} onRetry={() => setVersion((n) => n + 1)} />}
      {load.status === "ready" &&
        (load.projects.length === 0 ? (
          <div className="rounded-card bg-surface">
            <EmptyState icon={FolderKanban} title="No projects" description="Create one to group related tasks." />
          </div>
        ) : (
          <ListSection>
            {load.projects.map((project) => (
              <Row
                key={project.id}
                href={`/tasks?project=${project.id}`}
                leading={<ProgressRing done={project.task_done} total={project.task_total} />}
                title={project.name}
                subtitle={
                  project.task_total === 0
                    ? "No tasks yet"
                    : `${project.task_open} open · ${project.task_done} of ${project.task_total} done`
                }
                trailing={
                  project.status !== "active" ? (
                    <span className="rounded-full bg-fill px-2 py-0.5 text-caption font-semibold capitalize text-label-2">
                      {project.status}
                    </span>
                  ) : undefined
                }
              />
            ))}
          </ListSection>
        ))}
    </>
  );
}
