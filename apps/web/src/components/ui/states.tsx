import { clsx } from "clsx";
import { AlertTriangle, CheckCircle2, CircleDashed, Inbox, type LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

import { Button } from "@/components/ui/button";
import type { ApiError } from "@/lib/api";

/** Every data view shows exactly one of these: loading, empty, success, partial, or error. */

export function LoadingState({ label = "Loading…" }: { label?: string }) {
  return (
    <div role="status" aria-live="polite" className="flex items-center justify-center gap-2.5 p-8 text-subhead text-label-2">
      <span
        aria-hidden="true"
        className="size-4 animate-spin rounded-full border-2 border-label-3 border-t-transparent motion-reduce:animate-none"
      />
      {label}
    </div>
  );
}

export function EmptyState({
  title,
  description,
  icon: Icon = Inbox,
  action,
}: {
  title: string;
  description: string;
  icon?: LucideIcon;
  action?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center gap-2 px-6 py-12 text-center">
      <Icon aria-hidden="true" className="size-9 text-label-3" />
      <p className="text-headline font-semibold text-label">{title}</p>
      <p className="max-w-sm text-subhead text-label-2">{description}</p>
      {action && <div className="mt-2">{action}</div>}
    </div>
  );
}

export function ErrorState({ error, onRetry }: { error: ApiError; onRetry?: () => void }) {
  return (
    <div role="alert" className="flex flex-col items-center gap-2 px-6 py-10 text-center">
      <AlertTriangle aria-hidden="true" className="size-9 text-orange" />
      <p className="text-headline font-semibold text-label">Something went wrong</p>
      <p className="max-w-sm text-subhead text-label-2">{error.message}</p>
      {error.requestId && <p className="text-caption text-label-3">Reference {error.requestId}</p>}
      {onRetry && (
        <Button variant="tinted" className="mt-2" onClick={onRetry}>
          Try again
        </Button>
      )}
    </div>
  );
}

type Tone = "success" | "partial" | "error" | "info";

const tones: Record<Tone, { className: string; icon: LucideIcon }> = {
  success: { className: "bg-green-tint text-green", icon: CheckCircle2 },
  partial: { className: "bg-orange-tint text-orange", icon: CircleDashed },
  error: { className: "bg-red-tint text-red", icon: AlertTriangle },
  info: { className: "bg-blue-tint text-blue", icon: CircleDashed },
};

export function Notice({ tone, children }: { tone: Tone; children: ReactNode }) {
  const { className, icon: Icon } = tones[tone];
  return (
    <div
      role={tone === "error" ? "alert" : "status"}
      className={clsx("flex items-start gap-2 rounded-control px-3.5 py-2.5 text-subhead", className)}
    >
      <Icon aria-hidden="true" className="mt-0.5 size-4 flex-none" />
      <span className="text-label">{children}</span>
    </div>
  );
}
