"use client";

import type { SettingsUpdate, UserSettings } from "@shared/types";
import { useEffect, useState, type FormEvent } from "react";

import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { SelectField } from "@/components/ui/field";
import { ListSection, Row } from "@/components/ui/list";
import { ErrorState, LoadingState, Notice } from "@/components/ui/states";
import { SwitchField } from "@/components/ui/switch";
import { api, ApiError } from "@/lib/api";
import { useSession } from "@/lib/session";
import { listTimeZones } from "@/lib/time";

const RETENTION_CHOICES = [7, 30, 90, 180, 365];
const FOREVER = "forever";

/** Only send fields the user actually changed, so concurrent edits elsewhere are not overwritten. */
export function diffSettings(original: UserSettings, draft: UserSettings): SettingsUpdate {
  const change: SettingsUpdate = {};
  if (draft.timezone !== original.timezone) change.timezone = draft.timezone;
  if (draft.default_model !== original.default_model) change.default_model = draft.default_model;
  if (draft.notify_run_succeeded !== original.notify_run_succeeded) change.notify_run_succeeded = draft.notify_run_succeeded;
  if (draft.notify_run_failed !== original.notify_run_failed) change.notify_run_failed = draft.notify_run_failed;
  if (draft.notify_approval_needed !== original.notify_approval_needed)
    change.notify_approval_needed = draft.notify_approval_needed;
  if (draft.message_retention_days !== original.message_retention_days)
    change.message_retention_days = draft.message_retention_days;
  return change;
}

type LoadState = { status: "loading" } | { status: "ready"; settings: UserSettings } | { status: "error"; error: ApiError };
type SaveState = { status: "idle" } | { status: "saving" } | { status: "saved" } | { status: "error"; error: ApiError };

export function SettingsForm() {
  const { state: session, setUser } = useSession();
  const [load, setLoad] = useState<LoadState>({ status: "loading" });
  const [draft, setDraft] = useState<UserSettings | null>(null);
  const [save, setSave] = useState<SaveState>({ status: "idle" });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    api<UserSettings>("/api/settings", { signal: controller.signal })
      .then((settings) => {
        setLoad({ status: "ready", settings });
        setDraft(settings);
      })
      .catch((error: unknown) => {
        if (!controller.signal.aborted)
          setLoad({ status: "error", error: error instanceof ApiError ? error : new ApiError(0, "internal_error", "Unknown error") });
      });
    return () => controller.abort();
  }, [attempt]);

  if (load.status === "loading" || (load.status === "ready" && !draft)) return <LoadingState label="Loading settings…" />;
  if (load.status === "error")
    return (
      <ErrorState
        error={load.error}
        onRetry={() => {
          setLoad({ status: "loading" });
          setAttempt((n) => n + 1);
        }}
      />
    );
  if (!draft) return null;

  const original = load.settings;
  const timeZones = listTimeZones(draft.timezone);
  const change = diffSettings(original, draft);
  const dirty = Object.keys(change).length > 0;
  const fieldError = (name: string) =>
    save.status === "error" ? save.error.fields.find((f) => f.field === name)?.message : undefined;

  const update = <K extends keyof UserSettings>(key: K, value: UserSettings[K]) => {
    setDraft({ ...draft, [key]: value });
    if (save.status !== "saving") setSave({ status: "idle" });
  };

  const onSubmit = async (event: FormEvent) => {
    event.preventDefault();
    if (!dirty) return;
    setSave({ status: "saving" });
    try {
      const saved = await api<UserSettings>("/api/settings", { method: "PATCH", body: change });
      setLoad({ status: "ready", settings: saved });
      setDraft(saved);
      setSave({ status: "saved" });
      // Update the shell's user in place; reloading the session would unmount this form and hide the result.
      if (change.timezone && session.status === "authenticated") setUser({ ...session.user, timezone: saved.timezone });
    } catch (error) {
      setSave({ status: "error", error: error instanceof ApiError ? error : new ApiError(0, "internal_error", "Unknown error") });
    }
  };

  const retentionOptions = [
    { value: FOREVER, label: "Keep until I delete them" },
    ...Array.from(new Set([...RETENTION_CHOICES, ...(draft.message_retention_days ? [draft.message_retention_days] : [])]))
      .sort((a, b) => a - b)
      .map((d) => ({ value: String(d), label: `Delete after ${d} days` })),
  ];

  return (
    <>
      <PageHeader title="Settings" description="Your preferences. Changes apply only to your account." />
      <form onSubmit={onSubmit} className="flex max-w-2xl flex-col gap-4" noValidate>
        <ListSection header="General">
          <div className="flex flex-col gap-4 p-4">
            <SelectField
              label="Timezone"
              hint="Used for greetings, due dates, and scheduled automations."
              value={draft.timezone}
              onChange={(e) => update("timezone", e.target.value)}
              error={fieldError("timezone")}
              options={timeZones.map((z) => ({ value: z, label: z }))}
            />
            <SelectField
              label="Assistant model"
              hint="Only models enabled on this server are listed. The API key never leaves the server."
              value={draft.default_model}
              onChange={(e) => update("default_model", e.target.value)}
              error={fieldError("default_model")}
              options={original.available_models.map((m) => ({ value: m, label: m }))}
            />
          </div>
        </ListSection>

        <ListSection header="Notifications" footer="Choose which automation events notify you.">
            <SwitchField
              label="Run succeeded"
              checked={draft.notify_run_succeeded}
              onCheckedChange={(v) => update("notify_run_succeeded", v)}
            />
            <SwitchField
              label="Run failed"
              checked={draft.notify_run_failed}
              onCheckedChange={(v) => update("notify_run_failed", v)}
            />
            <SwitchField
              label="Approval needed"
              description="Recommended: high-risk actions wait until you respond."
              checked={draft.notify_approval_needed}
              onCheckedChange={(v) => update("notify_approval_needed", v)}
            />
        </ListSection>

        <ListSection header="Memory">
          <Row
            href="/memories"
            title="Manage memory"
            subtitle="Review, edit, delete or export what the assistant remembers"
          />
        </ListSection>

        <ListSection header="Data retention">
          <div className="p-4">
          <SelectField
            label="Conversation messages"
            hint="How long chat messages are kept. Approved memories are managed separately."
            value={draft.message_retention_days === null ? FOREVER : String(draft.message_retention_days)}
            onChange={(e) => update("message_retention_days", e.target.value === FOREVER ? null : Number(e.target.value))}
            error={fieldError("message_retention_days")}
            options={retentionOptions}
          />
          </div>
        </ListSection>

        <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
          <Button type="submit" loading={save.status === "saving"} disabled={!dirty}>
            Save changes
          </Button>
          {dirty && save.status !== "saving" && (
            <Button type="button" variant="plain" onClick={() => setDraft(original)}>
              Discard
            </Button>
          )}
        </div>
        {save.status === "saved" && <Notice tone="success">Settings saved.</Notice>}
        {save.status === "error" && <Notice tone="error">{save.error.message}</Notice>}
      </form>
    </>
  );
}
