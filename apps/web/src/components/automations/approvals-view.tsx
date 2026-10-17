"use client";

import type { Approval, ApprovalStatus } from "@shared/types";
import { ShieldCheck } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { ApprovalChip } from "@/components/ui/status-chip";
import { Segmented } from "@/components/ui/segmented";
import { EmptyState, ErrorState, LoadingState, Notice } from "@/components/ui/states";
import { api, ApiError } from "@/lib/api";
import { toApiError } from "@/lib/errors";

const TABS: { value: ApprovalStatus; label: string }[] = [
  { value: "pending", label: "Waiting" },
  { value: "consumed", label: "Done" },
  { value: "rejected", label: "Rejected" },
  { value: "expired", label: "Expired" },
];

type LoadState = { status: "loading" } | { status: "ready"; rows: Approval[] } | { status: "error"; error: ApiError };

function timeLeft(expiresAt: string): string {
  const minutes = Math.round((new Date(expiresAt).getTime() - Date.now()) / 60000);
  if (minutes <= 0) return "Expired";
  if (minutes < 60) return `Expires in ${minutes} min`;
  return `Expires in ${Math.round(minutes / 60)} h`;
}

export function ApprovalsView() {
  const [tab, setTab] = useState<ApprovalStatus>("pending");
  return <ApprovalsList key={tab} tab={tab} onTabChange={setTab} />;
}

function ApprovalsList({ tab, onTabChange }: { tab: ApprovalStatus; onTabChange: (tab: ApprovalStatus) => void }) {
  const [load, setLoad] = useState<LoadState>({ status: "loading" });
  const [version, setVersion] = useState(0);
  const [notice, setNotice] = useState<{ tone: "success" | "error"; text: string } | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    api<Approval[]>(`/api/approvals?status=${tab}`, { signal: controller.signal })
      .then((rows) => setLoad({ status: "ready", rows }))
      .catch((e: unknown) => {
        if (!controller.signal.aborted) setLoad({ status: "error", error: toApiError(e) });
      });
    return () => controller.abort();
  }, [tab, version]);

  const decide = useCallback(async (approval: Approval, decision: "approve" | "reject") => {
    try {
      await api<Approval>(`/api/approvals/${approval.id}/${decision}`, { method: "POST", body: {} });
      setNotice({
        tone: "success",
        text:
          decision === "approve"
            ? "Approved. The action ran once and cannot run again from this approval."
            : "Rejected. The action did not run.",
      });
      setVersion((n) => n + 1);
    } catch (e) {
      setNotice({ tone: "error", text: toApiError(e).message });
      setVersion((n) => n + 1);
    }
  }, []);

  return (
    <>
      <PageHeader
        title="Approvals"
        description="Nothing high-risk runs until you approve it here. Each approval works once and then expires."
      />
      <Segmented label="Filter approvals" value={tab} options={TABS} onChange={onTabChange} className="mb-4" />
      {notice && (
        <div className="mb-4">
          <Notice tone={notice.tone}>{notice.text}</Notice>
        </div>
      )}

      {load.status === "loading" && <LoadingState label="Loading approvals…" />}
      {load.status === "error" && <ErrorState error={load.error} onRetry={() => setVersion((n) => n + 1)} />}
      {load.status === "ready" &&
        (load.rows.length === 0 ? (
          <div className="rounded-card bg-surface">
            <EmptyState
              icon={ShieldCheck}
              title={tab === "pending" ? "Nothing waiting" : "Nothing here"}
              description={
                tab === "pending"
                  ? "When an automation reaches a high-risk step, it stops and asks you here."
                  : "No approvals with this status."
              }
            />
          </div>
        ) : (
          <div className="flex flex-col gap-4">
            {load.rows.map((approval) => (
              <ApprovalCard key={approval.id} approval={approval} onDecide={decide} />
            ))}
          </div>
        ))}
    </>
  );
}

function ApprovalCard({
  approval,
  onDecide,
}: {
  approval: Approval;
  onDecide: (approval: Approval, decision: "approve" | "reject") => Promise<void>;
}) {
  const [pending, setPending] = useState<"approve" | "reject" | null>(null);
  const isPending = approval.status === "pending";

  const act = async (decision: "approve" | "reject") => {
    setPending(decision);
    try {
      await onDecide(approval, decision);
    } finally {
      setPending(null);
    }
  };

  return (
    <article className="animate-appear overflow-hidden rounded-card bg-surface">
      <header className="flex flex-wrap items-center justify-between gap-2 px-4 pt-4">
        <h2 className="text-headline font-semibold text-label">{approval.action_type.replace(/_/g, " ")}</h2>
        <ApprovalChip status={approval.status} />
      </header>

      <dl className="mt-3 flex flex-col text-subhead hairline border-y border-separator">
        <div className="flex gap-3 px-4 py-2.5">
          <dt className="w-24 flex-none text-label-2">Action</dt>
          <dd className="min-w-0 flex-1 break-words text-label">{approval.action_summary}</dd>
        </div>
        <div className="flex gap-3 px-4 py-2.5">
          <dt className="w-24 flex-none text-label-2">Target</dt>
          <dd className="min-w-0 flex-1 break-all font-medium text-label">{approval.target}</dd>
        </div>
        <div className="flex gap-3 px-4 py-2.5">
          <dt className="w-24 flex-none text-label-2">Why ask</dt>
          <dd className="min-w-0 flex-1 text-label">{approval.risk_explanation}</dd>
        </div>
        <div className="flex gap-3 px-4 py-2.5">
          <dt className="w-24 flex-none text-label-2">If you say yes</dt>
          <dd className="min-w-0 flex-1 text-label">{approval.likely_consequence}</dd>
        </div>
      </dl>

      <details className="border-b border-separator px-4 py-2.5">
        <summary className="min-h-11 cursor-pointer list-none text-subhead text-blue">
          Show the exact data to be sent
        </summary>
        <pre className="mt-2 overflow-x-auto rounded-control bg-surface-2 p-3 text-caption text-label">
          {approval.payload_preview}
        </pre>
        <p className="mt-2 text-caption text-label-3">
          Fingerprint {approval.payload_hash.slice(0, 16)}… — if anything changes, this approval stops working.
        </p>
      </details>

      <div className="flex flex-wrap items-center gap-2 px-4 py-3">
        {isPending ? (
          <>
            <Button loading={pending === "approve"} disabled={pending !== null} onClick={() => void act("approve")}>
              Approve once
            </Button>
            <Button
              variant="destructive"
              loading={pending === "reject"}
              disabled={pending !== null}
              onClick={() => void act("reject")}
            >
              Reject
            </Button>
            <span className="ml-auto text-footnote text-label-2">{timeLeft(approval.expires_at)}</span>
          </>
        ) : (
          <p className="text-footnote text-label-2">
            {approval.decided_at && `Decided ${new Date(approval.decided_at).toLocaleString()}`}
            {approval.decision_reason && ` — ${approval.decision_reason}`}
          </p>
        )}
      </div>
    </article>
  );
}
