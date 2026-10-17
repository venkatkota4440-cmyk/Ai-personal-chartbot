"use client";

import type { Memory, MemoryStatus, MemoryUpdate } from "@shared/types";
import { clsx } from "clsx";
import { BookMarked, Download, Pencil, Trash2 } from "lucide-react";
import { useEffect, useState, type FormEvent } from "react";

import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { TextField } from "@/components/ui/field";
import { EmptyState, ErrorState, LoadingState, Notice } from "@/components/ui/states";
import { api, ApiError } from "@/lib/api";
import { toApiError } from "@/lib/errors";

const FILTERS: { value: MemoryStatus; label: string; empty: string }[] = [
  { value: "approved", label: "Approved", empty: "No approved memories. Add one below or approve a suggestion." },
  { value: "proposed", label: "Suggested", empty: "No suggestions waiting for review." },
  { value: "rejected", label: "Rejected", empty: "Nothing rejected." },
];

const statusStyle: Record<MemoryStatus, string> = {
  approved: "border-green text-green",
  proposed: "border-orange text-orange",
  rejected: "border-separator text-label-2",
};

type LoadState = { status: "loading" } | { status: "ready"; items: Memory[] } | { status: "error"; error: ApiError };

export function MemoryManager() {
  const [filter, setFilter] = useState<MemoryStatus>("approved");
  const [load, setLoad] = useState<LoadState>({ status: "loading" });
  const [version, setVersion] = useState(0);
  const [notice, setNotice] = useState<{ tone: "success" | "error"; text: string } | null>(null);
  const [newContent, setNewContent] = useState("");
  const [adding, setAdding] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    api<Memory[]>("/api/memories", { signal: controller.signal })
      .then((items) => setLoad({ status: "ready", items }))
      .catch((e: unknown) => {
        if (!controller.signal.aborted) setLoad({ status: "error", error: toApiError(e) });
      });
    return () => controller.abort();
  }, [version]);

  const reload = () => setVersion((n) => n + 1);

  const replace = (updated: Memory) =>
    setLoad((current) =>
      current.status === "ready"
        ? { status: "ready", items: current.items.map((m) => (m.id === updated.id ? updated : m)) }
        : current,
    );

  const onAdd = async (event: FormEvent) => {
    event.preventDefault();
    if (!newContent.trim()) return;
    setAdding(true);
    setNotice(null);
    try {
      const created = await api<Memory>("/api/memories", { method: "POST", body: { content: newContent.trim() } });
      setLoad((current) => (current.status === "ready" ? { status: "ready", items: [created, ...current.items] } : current));
      setNewContent("");
      setFilter("approved");
      setNotice({ tone: "success", text: "Memory added." });
    } catch (e) {
      setNotice({ tone: "error", text: toApiError(e).message });
    } finally {
      setAdding(false);
    }
  };

  const counts = (status: MemoryStatus) => (load.status === "ready" ? load.items.filter((m) => m.status === status).length : 0);
  const active = FILTERS.find((f) => f.value === filter) ?? FILTERS[0]!;

  return (
    <>
      <PageHeader
        title="Memory"
        description="What your assistant may remember about you. Only approved memories are ever used, and every reply shows which ones it used."
        actions={
          <a
            href="/api/memories/export"
            download
            className="inline-flex min-h-11 items-center gap-2 rounded-lg border border-separator bg-surface-2 px-4 text-subhead font-semibold text-label hover:border-blue"
          >
            <Download aria-hidden="true" className="size-4" />
            Export JSON
          </a>
        }
      />

      <form onSubmit={onAdd} className="mb-6 flex flex-col gap-3 rounded-2xl border border-separator bg-surface p-5 sm:flex-row sm:items-end">
        <div className="flex-1">
          <TextField
            label="Add a memory"
            hint="Something useful to remember, e.g. “I prefer Python examples”. Up to 1000 characters."
            value={newContent}
            maxLength={1000}
            onChange={(e) => setNewContent(e.target.value)}
          />
        </div>
        <Button type="submit" loading={adding} disabled={!newContent.trim()}>
          Add memory
        </Button>
      </form>
      {notice && (
        <div className="mb-4">
          <Notice tone={notice.tone}>{notice.text}</Notice>
        </div>
      )}

      <div role="group" aria-label="Filter memories by status" className="mb-4 flex flex-wrap gap-2">
        {FILTERS.map((f) => (
          <button
            key={f.value}
            type="button"
            aria-pressed={filter === f.value}
            onClick={() => setFilter(f.value)}
            className={clsx(
              "min-h-11 rounded-full border px-4 text-subhead font-medium",
              filter === f.value ? "border-blue bg-blue-tint text-label" : "border-separator text-label-2 hover:text-label",
            )}
          >
            {f.label} ({counts(f.value)})
          </button>
        ))}
      </div>

      {load.status === "loading" && <LoadingState label="Loading memories…" />}
      {load.status === "error" && <ErrorState error={load.error} onRetry={reload} />}
      {load.status === "ready" &&
        (load.items.filter((m) => m.status === filter).length === 0 ? (
          <EmptyState icon={BookMarked} title={`No ${active.label.toLowerCase()} memories`} description={active.empty} />
        ) : (
          <ul className="flex flex-col gap-3">
            {load.items
              .filter((m) => m.status === filter)
              .map((m) => (
                <MemoryRow
                  key={m.id}
                  memory={m}
                  onUpdated={replace}
                  onDeleted={() => {
                    setLoad((current) =>
                      current.status === "ready" ? { status: "ready", items: current.items.filter((x) => x.id !== m.id) } : current,
                    );
                    setNotice({ tone: "success", text: "Memory deleted." });
                  }}
                />
              ))}
          </ul>
        ))}
    </>
  );
}

function MemoryRow({
  memory,
  onUpdated,
  onDeleted,
}: {
  memory: Memory;
  onUpdated: (m: Memory) => void;
  onDeleted: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState(memory.content);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const patch = async (change: MemoryUpdate) => {
    setPending(true);
    setError(null);
    try {
      onUpdated(await api<Memory>(`/api/memories/${memory.id}`, { method: "PATCH", body: change }));
      setEditing(false);
    } catch (e) {
      setError(toApiError(e).message);
    } finally {
      setPending(false);
    }
  };

  return (
    <li className="rounded-2xl border border-separator bg-surface p-4">
      {editing ? (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            void patch({ content: text.trim() });
          }}
          className="flex flex-col gap-3"
        >
          <TextField label="Edit memory" value={text} maxLength={1000} onChange={(e) => setText(e.target.value)} />
          <div className="flex gap-2">
            <Button type="submit" loading={pending} disabled={!text.trim()}>
              Save
            </Button>
            <Button
              type="button"
              variant="plain"
              onClick={() => {
                setText(memory.content);
                setEditing(false);
              }}
            >
              Cancel
            </Button>
          </div>
        </form>
      ) : (
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div className="min-w-0">
            <p className="break-words text-label">{memory.content}</p>
            <p className="mt-1 flex flex-wrap items-center gap-2 text-footnote text-label-2">
              <span className={clsx("rounded-full border px-2 py-0.5 capitalize", statusStyle[memory.status])}>
                {memory.status === "proposed" ? "suggested" : memory.status}
              </span>
              {memory.source === "chat" ? "Suggested in chat" : "Added by you"} · updated{" "}
              {new Date(memory.updated_at).toLocaleDateString()}
            </p>
          </div>
          <div className="flex shrink-0 flex-wrap gap-2">
            {memory.status !== "approved" && (
              <Button variant="filled" disabled={pending} onClick={() => void patch({ status: "approved" })}>
                Approve
              </Button>
            )}
            {memory.status !== "rejected" && (
              <Button variant="tinted" disabled={pending} onClick={() => void patch({ status: "rejected" })}>
                Reject
              </Button>
            )}
            <Button variant="plain" aria-label={`Edit memory: ${memory.content}`} className="px-3" onClick={() => setEditing(true)}>
              <Pencil aria-hidden="true" className="size-4" />
            </Button>
            <ConfirmDialog
              trigger={
                <Button variant="plain" aria-label={`Delete memory: ${memory.content}`} className="px-3">
                  <Trash2 aria-hidden="true" className="size-4" />
                </Button>
              }
              title="Delete this memory?"
              description="Its text is erased permanently. Past replies will show it as a deleted memory."
              confirmLabel="Delete memory"
              onConfirm={async () => {
                try {
                  await api<void>(`/api/memories/${memory.id}`, { method: "DELETE" });
                  onDeleted();
                } catch (e) {
                  setError(toApiError(e).message);
                }
              }}
            />
          </div>
        </div>
      )}
      {error && (
        <p role="alert" className="mt-2 text-subhead text-red">
          {error}
        </p>
      )}
    </li>
  );
}
