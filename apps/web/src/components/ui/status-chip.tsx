import type { ApprovalStatus, RiskLevel, RunStatus } from "@shared/types";
import { clsx } from "clsx";

const base = "inline-flex items-center rounded-full px-2 py-0.5 text-caption font-semibold";

const runStyles: Record<RunStatus, { label: string; className: string }> = {
  queued: { label: "Queued", className: "bg-fill text-label-2" },
  running: { label: "Running", className: "bg-blue-tint text-blue" },
  awaiting_approval: { label: "Needs approval", className: "bg-orange-tint text-orange" },
  succeeded: { label: "Done", className: "bg-green-tint text-green" },
  partially_succeeded: { label: "Partly done", className: "bg-orange-tint text-orange" },
  failed: { label: "Failed", className: "bg-red-tint text-red" },
  cancelled: { label: "Cancelled", className: "bg-fill text-label-2" },
};

/** Status is always spelled out, never colour alone. */
export function StatusChip({ status }: { status: RunStatus }) {
  const { label, className } = runStyles[status];
  return <span className={clsx(base, className)}>{label}</span>;
}

const riskStyles: Record<RiskLevel, { label: string; className: string }> = {
  low: { label: "Low risk", className: "bg-green-tint text-green" },
  medium: { label: "Medium risk", className: "bg-orange-tint text-orange" },
  high: { label: "Needs approval", className: "bg-red-tint text-red" },
  prohibited: { label: "Blocked", className: "bg-red-tint text-red" },
};

export function RiskChip({ risk }: { risk: RiskLevel }) {
  const { label, className } = riskStyles[risk];
  return <span className={clsx(base, className)}>{label}</span>;
}

const approvalStyles: Record<ApprovalStatus, { label: string; className: string }> = {
  pending: { label: "Waiting for you", className: "bg-orange-tint text-orange" },
  approved: { label: "Approved", className: "bg-green-tint text-green" },
  consumed: { label: "Done once", className: "bg-green-tint text-green" },
  rejected: { label: "Rejected", className: "bg-fill text-label-2" },
  expired: { label: "Expired", className: "bg-fill text-label-2" },
};

export function ApprovalChip({ status }: { status: ApprovalStatus }) {
  const { label, className } = approvalStyles[status];
  return <span className={clsx(base, className)}>{label}</span>;
}
