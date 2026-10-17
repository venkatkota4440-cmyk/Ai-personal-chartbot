"use client";

import type { Automation, AutomationDetail, Run, RunDetail } from "@shared/types";
import { clsx } from "clsx";
import { CalendarClock, Play, Workflow } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { ListSection, Row } from "@/components/ui/list";
import { RiskChip, StatusChip } from "@/components/ui/status-chip";
import { EmptyState, ErrorState, LoadingState, Notice } from "@/components/ui/states";
import { SwitchField } from "@/components/ui/switch";
import { api, ApiError } from "@/lib/api";
import { toApiError } from "@/lib/errors";

type LoadState =
  | { status: "loading" }
  | { status: "ready"; rows: Automation[] }
  | { status: "error"; error: ApiError };

export function AutomationsView() {
  const [load, setLoad] = useState<LoadState>({ status: "loading" });
  const [version, setVersion] = useState(0);
  const [openId, setOpenId] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    api<Automation[]>("/api/automations", { signal: controller.signal })
      .then((rows) => setLoad({ status: "ready", rows }))
      .catch((e: unknown) => {
        if (!controller.signal.aborted) setLoad({ status: "error", error: toApiError(e) });
      });
    return () => controller.abort();
  }, [version]);

  if (load.status === "loading") return <LoadingState label="Loading automations…" />;
  if (load.status === "error")
    return <ErrorState error={load.error} onRetry={() => setVersion((n) => n + 1)} />;

  if (openId) {
    return <AutomationDetailView id={openId} onBack={() => setOpenId(null)} onChanged={() => setVersion((n) => n + 1)} />;
  }

  return (
    <>
      <PageHeader
        title="Automations"
        description="Routine work that runs on a schedule or on demand. High-risk steps always stop for your approval."
      />
      {load.rows.length === 0 ? (
        <div className="rounded-card bg-surface">
          <EmptyState icon={Workflow} title="No automations" description="Your starter automations will appear here." />
        </div>
      ) : (
        <ListSection footer="Scheduled automations run in your own timezone.">
          {load.rows.map((row) => (
            <Row
              key={row.id}
              onClick={() => setOpenId(row.id)}
              leading={
                <span
                  className={clsx(
                    "grid size-9 flex-none place-items-center rounded-[0.5rem]",
                    row.enabled ? "bg-blue text-white" : "bg-fill text-label-2",
                  )}
                >
                  {row.trigger_type === "schedule" ? (
                    <CalendarClock aria-hidden="true" className="size-5" />
                  ) : (
                    <Workflow aria-hidden="true" className="size-5" />
                  )}
                </span>
              }
              title={row.name}
              subtitle={
                row.trigger_type === "schedule"
                  ? `${row.enabled ? "On" : "Off"} · schedule ${row.cron}`
                  : `${row.enabled ? "On" : "Off"} · run by hand`
              }
            />
          ))}
        </ListSection>
      )}
    </>
  );
}

type DetailState =
  | { status: "loading" }
  | { status: "ready"; detail: AutomationDetail; runs: Run[] }
  | { status: "error"; error: ApiError };

function AutomationDetailView({
  id,
  onBack,
  onChanged,
}: {
  id: string;
  onBack: () => void;
  onChanged: () => void;
}) {
  const [state, setState] = useState<DetailState>({ status: "loading" });
  const [version, setVersion] = useState(0);
  const [openRun, setOpenRun] = useState<string | null>(null);
  const [notice, setNotice] = useState<{ tone: "success" | "partial" | "error" | "info"; text: string } | null>(null);
  const [running, setRunning] = useState(false);

  const reload = useCallback(() => setVersion((n) => n + 1), []);

  useEffect(() => {
    const controller = new AbortController();
    Promise.all([
      api<AutomationDetail>(`/api/automations/${id}`, { signal: controller.signal }),
      api<Run[]>(`/api/automations/${id}/runs`, { signal: controller.signal }),
    ])
      .then(([detail, runs]) => setState({ status: "ready", detail, runs }))
      .catch((e: unknown) => {
        if (!controller.signal.aborted) setState({ status: "error", error: toApiError(e) });
      });
    return () => controller.abort();
  }, [id, version]);

  const toggle = async (enabled: boolean) => {
    try {
      await api<AutomationDetail>(`/api/automations/${id}`, { method: "PATCH", body: { enabled } });
      reload();
      onChanged();
    } catch (e) {
      setNotice({ tone: "error", text: toApiError(e).message });
    }
  };

  const runNow = async () => {
    setRunning(true);
    setNotice(null);
    try {
      // A fresh key each time, so an intentional second run is allowed but a retry is not duplicated.
      const run = await api<Run>(`/api/automations/${id}/run`, {
        method: "POST",
        idempotencyKey: `manual-${Date.now()}`,
      });
      const messages: Record<string, { tone: "success" | "partial" | "error" | "info"; text: string }> = {
        succeeded: { tone: "success", text: "Run finished successfully." },
        partially_succeeded: { tone: "partial", text: "Run finished, but some steps did not complete." },
        awaiting_approval: { tone: "info", text: "Run paused: it needs your approval before the next step." },
        failed: { tone: "error", text: "Run failed. Open it to see which step." },
        cancelled: { tone: "error", text: "Run was cancelled." },
        queued: { tone: "info", text: "Run queued." },
        running: { tone: "info", text: "Run started." },
      };
      setNotice(messages[run.status] ?? { tone: "info", text: `Run ${run.status}.` });
      setOpenRun(run.id);
      reload();
    } catch (e) {
      setNotice({ tone: "error", text: toApiError(e).message });
    } finally {
      setRunning(false);
    }
  };

  if (state.status === "loading") return <LoadingState label="Loading automation…" />;
  if (state.status === "error") return <ErrorState error={state.error} onRetry={reload} />;

  const { detail, runs } = state;

  return (
    <>
      <Button variant="plain" className="mb-2 px-0" onClick={onBack}>
        ‹ All automations
      </Button>
      <PageHeader
        title={detail.name}
        description={detail.next_run_hint ?? "Runs only when you start it."}
        actions={
          <Button loading={running} onClick={() => void runNow()}>
            {!running && <Play aria-hidden="true" className="size-4" />}
            Run now
          </Button>
        }
      />
      {notice && (
        <div className="mb-4">
          <Notice tone={notice.tone}>{notice.text}</Notice>
        </div>
      )}

      <div className="flex flex-col gap-5">
        <ListSection header="Schedule">
          <SwitchField
            label="Enabled"
            description={
              detail.trigger_type === "schedule"
                ? `Runs automatically at: ${detail.cron}`
                : "Manual automations only run when you press Run now."
            }
            checked={detail.enabled}
            onCheckedChange={(v) => void toggle(v)}
          />
        </ListSection>

        <ListSection header="Steps" footer="Risk is decided by the server, not by the automation.">
          {detail.step_risks.map((step, index) => (
            <Row
              key={`${step.type}-${index}`}
              leading={
                <span className="grid size-6 flex-none place-items-center rounded-full bg-fill text-caption font-semibold text-label-2">
                  {index + 1}
                </span>
              }
              title={step.type.replace(/_/g, " ")}
              subtitle={step.reason}
              trailing={<RiskChip risk={step.risk} />}
            />
          ))}
        </ListSection>

        <ListSection header="Run history">
          {runs.length === 0 ? (
            <Row title="No runs yet" subtitle="Press Run now to try it safely." />
          ) : (
            runs.map((run) => (
              <Row
                key={run.id}
                onClick={() => setOpenRun(run.id)}
                title={new Date(run.created_at).toLocaleString()}
                subtitle={run.output_summary ?? `Triggered ${run.trigger}`}
                trailing={<StatusChip status={run.status} />}
              />
            ))
          )}
        </ListSection>
      </div>

      {openRun && <RunTimeline runId={openRun} onClose={() => setOpenRun(null)} onChanged={reload} />}
    </>
  );
}

function RunTimeline({ runId, onClose, onChanged }: { runId: string; onClose: () => void; onChanged: () => void }) {
  const [detail, setDetail] = useState<RunDetail | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [version, setVersion] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    api<RunDetail>(`/api/runs/${runId}`, { signal: controller.signal })
      .then(setDetail)
      .catch((e: unknown) => {
        if (!controller.signal.aborted) setError(toApiError(e));
      });
    return () => controller.abort();
  }, [runId, version]);

  const cancel = async () => {
    try {
      await api<Run>(`/api/runs/${runId}/cancel`, { method: "POST" });
      setVersion((n) => n + 1);
      onChanged();
    } catch (e) {
      setError(toApiError(e));
    }
  };

  const canCancel =
    detail !== null && ["queued", "running", "awaiting_approval"].includes(detail.status) && !detail.cancel_requested;

  return (
    <section aria-label="Run timeline" className="mt-5 rounded-card bg-surface p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-headline font-semibold text-label">Run timeline</h2>
        <div className="flex items-center gap-2">
          {detail && <StatusChip status={detail.status} />}
          <Button variant="plain" onClick={onClose}>
            Close
          </Button>
        </div>
      </div>

      {error && <Notice tone="error">{error.message}</Notice>}
      {!detail && !error && <LoadingState label="Loading run…" />}

      {detail && (
        <>
          {detail.output_summary && <p className="mt-2 text-subhead text-label-2">{detail.output_summary}</p>}
          <ol className="mt-4 flex flex-col gap-3">
            {detail.steps.map((step) => (
              <li key={step.id} className="flex gap-3">
                <span
                  className={clsx(
                    "mt-1 size-2.5 flex-none rounded-full",
                    step.status === "succeeded" && "bg-green",
                    step.status === "failed" && "bg-red",
                    step.status === "blocked" && "bg-red",
                    step.status === "awaiting_approval" && "bg-orange",
                    ["pending", "skipped", "cancelled", "running"].includes(step.status) && "bg-label-3",
                  )}
                />
                <div className="min-w-0 flex-1">
                  <p className="flex flex-wrap items-center gap-2 text-subhead font-medium text-label">
                    {step.step_index + 1}. {step.type.replace(/_/g, " ")}
                    {step.risk_level && <RiskChip risk={step.risk_level} />}
                    {step.attempts > 1 && (
                      <span className="text-caption text-label-2">{step.attempts} attempts</span>
                    )}
                  </p>
                  <p className="mt-0.5 whitespace-pre-wrap break-words text-footnote text-label-2">
                    {step.output_summary ?? step.error_message_sanitized ?? step.status.replace(/_/g, " ")}
                  </p>
                </div>
              </li>
            ))}
          </ol>

          {detail.pending_approval_id && (
            <div className="mt-4">
              <Notice tone="info">
                This run is waiting for your approval. Open Approvals to decide.
              </Notice>
            </div>
          )}
          {canCancel && (
            <Button variant="destructive" className="mt-4" onClick={() => void cancel()}>
              Cancel run
            </Button>
          )}
        </>
      )}
    </section>
  );
}
