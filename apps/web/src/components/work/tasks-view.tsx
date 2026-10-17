"use client";

import type { Project, Task, TaskPriority, TaskStatus } from "@shared/types";
import { clsx } from "clsx";
import { Check, ListChecks, Plus } from "lucide-react";
import { useEffect, useMemo, useState, type FormEvent } from "react";

import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { SelectField, TextField } from "@/components/ui/field";
import { ListSection, Row } from "@/components/ui/list";
import { Segmented } from "@/components/ui/segmented";
import { EmptyState, ErrorState, LoadingState, Notice } from "@/components/ui/states";
import { api, ApiError } from "@/lib/api";
import { toApiError } from "@/lib/errors";

type Filter = "open" | "today" | "done" | "all";

const FILTERS: { value: Filter; label: string }[] = [
  { value: "open", label: "Open" },
  { value: "today", label: "Today" },
  { value: "done", label: "Done" },
  { value: "all", label: "All" },
];

const PRIORITIES: TaskPriority[] = ["low", "medium", "high", "urgent"];

const priorityStyle: Record<TaskPriority, string> = {
  low: "text-label-3",
  medium: "text-label-2",
  high: "text-orange",
  urgent: "text-red",
};

const statusLabel: Record<TaskStatus, string> = {
  todo: "To do",
  in_progress: "In progress",
  blocked: "Blocked",
  done: "Done",
};

function dueLabel(due: string | null): { text: string; overdue: boolean } | null {
  if (!due) return null;
  const date = new Date(due);
  const now = new Date();
  const overdue = date.getTime() < now.getTime();
  const sameDay = date.toDateString() === now.toDateString();
  const text = sameDay
    ? `Today, ${date.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })}`
    : date.toLocaleDateString([], { month: "short", day: "numeric" });
  return { text, overdue };
}

type LoadState =
  | { status: "loading" }
  | { status: "ready"; tasks: Task[]; projects: Project[] }
  | { status: "error"; error: ApiError };

export function TasksView() {
  const [filter, setFilter] = useState<Filter>("open");
  const [load, setLoad] = useState<LoadState>({ status: "loading" });
  const [version, setVersion] = useState(0);
  const [adding, setAdding] = useState(false);
  const [notice, setNotice] = useState<{ tone: "success" | "error"; text: string } | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    Promise.all([
      api<Task[]>("/api/tasks", { signal: controller.signal }),
      api<Project[]>("/api/projects", { signal: controller.signal }),
    ])
      .then(([tasks, projects]) => setLoad({ status: "ready", tasks, projects }))
      .catch((e: unknown) => {
        if (!controller.signal.aborted) setLoad({ status: "error", error: toApiError(e) });
      });
    return () => controller.abort();
  }, [version]);

  const projectName = useMemo(() => {
    const map = new Map<string, string>();
    if (load.status === "ready") load.projects.forEach((p) => map.set(p.id, p.name));
    return map;
  }, [load]);

  const visible = useMemo(() => {
    if (load.status !== "ready") return [];
    const now = new Date();
    return load.tasks.filter((t) => {
      if (filter === "all") return true;
      if (filter === "done") return t.status === "done";
      if (filter === "open") return t.status !== "done";
      const due = t.due_at ? new Date(t.due_at) : null;
      return t.status !== "done" && due !== null && due.toDateString() <= now.toDateString();
    });
  }, [load, filter]);

  const patch = async (task: Task, change: Partial<Task>) => {
    setNotice(null);
    try {
      const updated = await api<Task>(`/api/tasks/${task.id}`, { method: "PATCH", body: change });
      setLoad((c) =>
        c.status === "ready" ? { ...c, tasks: c.tasks.map((t) => (t.id === updated.id ? updated : t)) } : c,
      );
    } catch (e) {
      setNotice({ tone: "error", text: toApiError(e).message });
    }
  };

  const remove = async (task: Task) => {
    try {
      await api<void>(`/api/tasks/${task.id}`, { method: "DELETE" });
      setLoad((c) => (c.status === "ready" ? { ...c, tasks: c.tasks.filter((t) => t.id !== task.id) } : c));
      setNotice({ tone: "success", text: "Task deleted." });
    } catch (e) {
      setNotice({ tone: "error", text: toApiError(e).message });
    }
  };

  return (
    <>
      <PageHeader
        title="Tasks"
        description="What needs doing. Changes save immediately."
        actions={
          <Button variant="tinted" onClick={() => setAdding((v) => !v)} aria-expanded={adding}>
            <Plus aria-hidden="true" className="size-4" />
            New task
          </Button>
        }
      />

      {adding && load.status === "ready" && (
        <NewTaskForm
          projects={load.projects}
          onCancel={() => setAdding(false)}
          onCreated={(task) => {
            setLoad((c) => (c.status === "ready" ? { ...c, tasks: [task, ...c.tasks] } : c));
            setAdding(false);
            setNotice({ tone: "success", text: "Task added." });
          }}
        />
      )}

      <Segmented label="Filter tasks" value={filter} options={FILTERS} onChange={setFilter} className="mb-4" />
      {notice && (
        <div className="mb-4">
          <Notice tone={notice.tone}>{notice.text}</Notice>
        </div>
      )}

      {load.status === "loading" && <LoadingState label="Loading tasks…" />}
      {load.status === "error" && <ErrorState error={load.error} onRetry={() => setVersion((n) => n + 1)} />}
      {load.status === "ready" &&
        (visible.length === 0 ? (
          <div className="rounded-card bg-surface">
            <EmptyState
              icon={ListChecks}
              title="Nothing here"
              description={filter === "done" ? "No finished tasks yet." : "No tasks match this filter."}
            />
          </div>
        ) : (
          <ListSection footer={`${visible.length} task${visible.length === 1 ? "" : "s"}`}>
            {visible.map((task) => {
              const due = dueLabel(task.due_at);
              const done = task.status === "done";
              return (
                <Row
                  key={task.id}
                  leading={
                    <button
                      type="button"
                      aria-label={done ? `Mark '${task.title}' as to do` : `Mark '${task.title}' as done`}
                      onClick={() => void patch(task, { status: done ? "todo" : "done" })}
                      className={clsx(
                        "grid size-6 place-items-center rounded-full border-2",
                        done ? "border-blue bg-blue text-white" : "border-label-3",
                      )}
                    >
                      {done && <Check aria-hidden="true" className="size-3.5" strokeWidth={3} />}
                    </button>
                  }
                  title={<span className={clsx(done && "text-label-3 line-through")}>{task.title}</span>}
                  subtitle={
                    <span className="flex flex-wrap items-center gap-x-2">
                      <span className={priorityStyle[task.priority]}>{task.priority}</span>
                      {task.project_id && <span>· {projectName.get(task.project_id) ?? "Project"}</span>}
                      {task.status !== "todo" && task.status !== "done" && <span>· {statusLabel[task.status]}</span>}
                      {due && <span className={due.overdue && !done ? "text-red" : ""}>· {due.text}</span>}
                    </span>
                  }
                  trailing={
                    <ConfirmDialog
                      trigger={
                        <button
                          type="button"
                          aria-label={`Delete task: ${task.title}`}
                          className="min-h-11 px-2 text-footnote text-red"
                        >
                          Delete
                        </button>
                      }
                      title="Delete this task?"
                      description="This cannot be undone."
                      confirmLabel="Delete"
                      onConfirm={() => remove(task)}
                    />
                  }
                />
              );
            })}
          </ListSection>
        ))}
    </>
  );
}

function NewTaskForm({
  projects,
  onCreated,
  onCancel,
}: {
  projects: Project[];
  onCreated: (task: Task) => void;
  onCancel: () => void;
}) {
  const [title, setTitle] = useState("");
  const [priority, setPriority] = useState<TaskPriority>("medium");
  const [projectId, setProjectId] = useState("");
  const [due, setDue] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!title.trim()) return;
    setPending(true);
    setError(null);
    try {
      onCreated(
        await api<Task>("/api/tasks", {
          method: "POST",
          body: {
            title: title.trim(),
            priority,
            project_id: projectId || null,
            // datetime-local has no timezone, so convert through Date to get a real offset.
            due_at: due ? new Date(due).toISOString() : null,
          },
        }),
      );
    } catch (e) {
      setError(toApiError(e).message);
      setPending(false);
    }
  };

  return (
    <form onSubmit={submit} className="mb-4 flex flex-col gap-3 rounded-card bg-surface p-4">
      <TextField label="Title" value={title} maxLength={300} onChange={(e) => setTitle(e.target.value)} autoFocus />
      <div className="grid gap-3 sm:grid-cols-3">
        <SelectField
          label="Priority"
          value={priority}
          onChange={(e) => setPriority(e.target.value as TaskPriority)}
          options={PRIORITIES.map((p) => ({ value: p, label: p }))}
        />
        <SelectField
          label="Project"
          value={projectId}
          onChange={(e) => setProjectId(e.target.value)}
          options={[{ value: "", label: "None" }, ...projects.map((p) => ({ value: p.id, label: p.name }))]}
        />
        <TextField label="Due" type="datetime-local" value={due} onChange={(e) => setDue(e.target.value)} />
      </div>
      {error && <Notice tone="error">{error}</Notice>}
      <div className="flex gap-2">
        <Button type="submit" loading={pending} disabled={!title.trim()}>
          Add task
        </Button>
        <Button type="button" variant="plain" onClick={onCancel}>
          Cancel
        </Button>
      </div>
    </form>
  );
}
