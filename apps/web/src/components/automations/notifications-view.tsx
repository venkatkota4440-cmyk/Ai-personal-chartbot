"use client";

import type { Notification } from "@shared/types";
import { Bell } from "lucide-react";
import { useEffect, useState } from "react";

import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { ListSection, Row } from "@/components/ui/list";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/states";
import { api, ApiError } from "@/lib/api";
import { toApiError } from "@/lib/errors";

type LoadState =
  | { status: "loading" }
  | { status: "ready"; rows: Notification[] }
  | { status: "error"; error: ApiError };

export function NotificationsView() {
  const [load, setLoad] = useState<LoadState>({ status: "loading" });
  const [version, setVersion] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    api<Notification[]>("/api/notifications", { signal: controller.signal })
      .then((rows) => setLoad({ status: "ready", rows }))
      .catch((e: unknown) => {
        if (!controller.signal.aborted) setLoad({ status: "error", error: toApiError(e) });
      });
    return () => controller.abort();
  }, [version]);

  const unread = load.status === "ready" ? load.rows.filter((n) => n.read_at === null).length : 0;

  return (
    <>
      <PageHeader
        title="Notifications"
        description="What your automations did while you were away."
        actions={
          unread > 0 ? (
            <Button
              variant="tinted"
              onClick={async () => {
                await api<{ updated: number }>("/api/notifications/read-all", { method: "POST" });
                setVersion((n) => n + 1);
              }}
            >
              Mark all read
            </Button>
          ) : undefined
        }
      />

      {load.status === "loading" && <LoadingState label="Loading notifications…" />}
      {load.status === "error" && <ErrorState error={load.error} onRetry={() => setVersion((n) => n + 1)} />}
      {load.status === "ready" &&
        (load.rows.length === 0 ? (
          <div className="rounded-card bg-surface">
            <EmptyState icon={Bell} title="No notifications" description="Run an automation and its result appears here." />
          </div>
        ) : (
          <ListSection>
            {load.rows.map((item) => (
              <Row
                key={item.id}
                href={item.link ?? undefined}
                leading={
                  <span
                    aria-label={item.read_at ? "Read" : "Unread"}
                    className={`size-2 flex-none rounded-full ${item.read_at ? "bg-transparent" : "bg-blue"}`}
                  />
                }
                title={item.message}
                subtitle={new Date(item.created_at).toLocaleString()}
              />
            ))}
          </ListSection>
        ))}
    </>
  );
}
