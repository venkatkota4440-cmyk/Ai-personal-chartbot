"use client";

import type { Memory } from "@shared/types";
import { Lightbulb } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { toApiError } from "@/lib/errors";

/** A memory the assistant suggested. Nothing is remembered until the user approves it here or on the Memory page. */
export function ProposalCard({ memory, onDecided }: { memory: Memory; onDecided: (updated: Memory) => void }) {
  const [pending, setPending] = useState<"approved" | "rejected" | null>(null);
  const [error, setError] = useState<string | null>(null);

  const decide = async (status: "approved" | "rejected") => {
    setPending(status);
    setError(null);
    try {
      onDecided(await api<Memory>(`/api/memories/${memory.id}`, { method: "PATCH", body: { status } }));
    } catch (e) {
      setError(toApiError(e).message);
    } finally {
      setPending(null);
    }
  };

  return (
    <div className="rounded-xl border border-separator bg-blue-tint p-3">
      <p className="flex items-center gap-2 text-footnote font-semibold uppercase tracking-wide text-blue">
        <Lightbulb aria-hidden="true" className="size-4" />
        Suggested memory
      </p>
      <p className="mt-1 text-subhead text-label">{memory.content}</p>
      <p className="mt-1 text-footnote text-label-2">Only used in future replies if you approve it.</p>
      <div className="mt-3 flex flex-wrap gap-2">
        <Button
          variant="filled"
          loading={pending === "approved"}
          disabled={pending !== null}
          onClick={() => decide("approved")}
          aria-label={`Approve memory: ${memory.content}`}
        >
          Approve
        </Button>
        <Button
          variant="tinted"
          loading={pending === "rejected"}
          disabled={pending !== null}
          onClick={() => decide("rejected")}
          aria-label={`Reject memory: ${memory.content}`}
        >
          Reject
        </Button>
      </div>
      {error && (
        <p role="alert" className="mt-2 text-subhead text-red">
          {error}
        </p>
      )}
    </div>
  );
}
