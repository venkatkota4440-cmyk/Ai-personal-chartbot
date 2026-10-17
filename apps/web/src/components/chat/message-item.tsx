import type { ChatMessage } from "@shared/types";
import { clsx } from "clsx";
import { BookMarked, ShieldAlert } from "lucide-react";

const confidenceLabel = { high: "High confidence", medium: "Medium confidence", low: "Low confidence" } as const;

export function MessageItem({ message }: { message: ChatMessage }) {
  const isUser = message.role === "user";
  return (
    <article
      aria-label={isUser ? "You said" : "Assistant replied"}
      className={clsx("flex animate-appear flex-col gap-2", isUser ? "items-end" : "items-start")}
    >
      <div
        className={clsx(
          "max-w-[min(42rem,92%)] whitespace-pre-wrap break-words rounded-2xl px-4 py-3 text-subhead leading-relaxed",
          isUser ? "bg-blue text-white" : "border border-separator bg-surface text-label",
        )}
      >
        {/* Rendered as plain text: model output is never interpreted as HTML or markdown. */}
        {message.content}
      </div>

      {!isUser && (
        <div className="flex max-w-[min(42rem,92%)] flex-col gap-2">
          <div className="flex flex-wrap items-center gap-2 text-footnote text-label-2">
            {message.confidence && (
              <span
                className={clsx(
                  "rounded-full border px-2 py-0.5",
                  message.confidence === "low" ? "border-orange text-orange" : "border-separator",
                )}
              >
                {confidenceLabel[message.confidence]}
              </span>
            )}
            {message.model && <span>Model: {message.model}</span>}
          </div>

          {message.human_review_note && (
            <p className="flex items-start gap-2 rounded-lg border border-orange bg-orange-tint px-3 py-2 text-subhead text-label">
              <ShieldAlert aria-hidden="true" className="mt-0.5 size-4 shrink-0 text-orange" />
              {message.human_review_note}
            </p>
          )}

          {message.memory_ranking && (
            <details className="rounded-lg border border-separator px-3 py-2 text-subhead">
              <summary className="flex min-h-11 cursor-pointer items-center gap-2 text-label-2 marker:content-none">
                <BookMarked aria-hidden="true" className="size-4 text-blue" />
                {message.used_memories.length === 0
                  ? "No memories used"
                  : `Used ${message.used_memories.length} approved ${message.used_memories.length === 1 ? "memory" : "memories"}`}
                {message.used_memories.length > 0 && <span className="text-xs">(matched by keyword)</span>}
              </summary>
              {message.used_memories.length > 0 && (
                <ul className="mt-2 list-disc space-y-1 pl-5 text-label">
                  {message.used_memories.map((m) => (
                    <li key={m.id}>
                      {m.content ?? <em className="text-label-2">Deleted memory</em>}
                      {m.status === "edited" && <span className="text-footnote text-label-2"> (edited since)</span>}
                    </li>
                  ))}
                </ul>
              )}
            </details>
          )}
        </div>
      )}
    </article>
  );
}
