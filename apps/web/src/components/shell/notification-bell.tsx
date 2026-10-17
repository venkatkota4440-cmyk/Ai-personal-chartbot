"use client";

import type { Notification } from "@shared/types";
import { Bell } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

import { api } from "@/lib/api";

/** Unread count in the navigation bar. Fails quietly: a missing badge must never block the page. */
export function NotificationBell() {
  const [count, setCount] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    api<Notification[]>("/api/notifications?unread=true", { signal: controller.signal })
      .then((rows) => setCount(rows.length))
      .catch(() => undefined);
    return () => controller.abort();
  }, []);

  return (
    <Link
      href="/notifications"
      className="relative inline-flex min-h-11 min-w-11 items-center justify-center rounded-full text-label"
      aria-label={count ? `Notifications, ${count} unread` : "Notifications"}
    >
      <Bell aria-hidden="true" className="size-5" />
      {count > 0 && (
        <span className="absolute right-1.5 top-1.5 grid min-w-4 place-items-center rounded-full bg-red px-1 text-[0.625rem] font-bold leading-4 text-white">
          {count > 9 ? "9+" : count}
        </span>
      )}
    </Link>
  );
}
