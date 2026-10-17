"use client";

import { LogOut } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState, type ReactNode } from "react";

import { Brand } from "@/components/shell/brand";
import { isActive, NAV_ITEMS, TAB_ITEMS } from "@/components/shell/nav-items";
import { NotificationBell } from "@/components/shell/notification-bell";
import { Button } from "@/components/ui/button";
import { ErrorState, LoadingState } from "@/components/ui/states";
import { ApiError } from "@/lib/api";
import { useSession } from "@/lib/session";
import { clsx } from "clsx";

function SignOutRow({ email }: { email: string }) {
  const { signOut } = useSession();
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  return (
    <div className="flex flex-col gap-1 border-t border-separator px-3 pt-3">
      <p className="truncate px-1 text-caption text-label-3" title={email}>
        {email}
      </p>
      <Button
        variant="plain"
        className="justify-start px-1"
        loading={pending}
        onClick={async () => {
          setPending(true);
          setError(null);
          try {
            await signOut();
          } catch (e) {
            setError(e instanceof ApiError ? e.message : "Sign out failed");
            setPending(false);
          }
        }}
      >
        {!pending && <LogOut aria-hidden="true" className="size-4" />}
        Sign out
      </Button>
      {error && (
        <p role="alert" className="px-1 text-caption text-red">
          {error}
        </p>
      )}
    </div>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  const { state, reload } = useSession();
  const pathname = usePathname();
  // usePathname is stable on the client; the shell only renders after the session resolves,
  // so highlighting can be computed directly.
  const mounted = true;

  if (state.status === "loading") {
    return (
      <main className="grid min-h-dvh place-items-center">
        <LoadingState label="Signing you in…" />
      </main>
    );
  }
  if (state.status === "error") {
    return (
      <main className="mx-auto grid min-h-dvh max-w-md place-items-center p-4">
        <ErrorState error={state.error} onRetry={reload} />
      </main>
    );
  }

  return (
    <div className="min-h-dvh lg:grid lg:grid-cols-[15rem_1fr]">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-50 focus:rounded-control focus:bg-blue focus:px-4 focus:py-2 focus:text-white"
      >
        Skip to content
      </a>

      {/* macOS-style source list */}
      <aside className="sticky top-0 hidden h-dvh flex-col gap-4 border-r border-separator bg-surface-2 p-3 lg:flex">
        <div className="px-2 pt-1">
          <Brand />
        </div>
        <nav aria-label="Main" className="flex-1">
          <ul className="flex flex-col gap-0.5">
            {NAV_ITEMS.map(({ href, label, icon: Icon }) => {
              const active = mounted && isActive(pathname, href);
              return (
                <li key={href}>
                  <Link
                    href={href}
                    aria-current={active ? "page" : undefined}
                    className={clsx(
                      "flex min-h-9 items-center gap-2.5 rounded-lg px-2.5 text-subhead font-medium",
                      active ? "bg-blue text-white" : "text-label hover:bg-fill",
                    )}
                  >
                    <Icon aria-hidden="true" className={clsx("size-4", !active && "text-label-2")} />
                    {label}
                  </Link>
                </li>
              );
            })}
          </ul>
        </nav>
        <SignOutRow email={state.user.email} />
      </aside>

      {/* iOS-style navigation bar */}
      <header className="material sticky top-0 z-30 flex items-center justify-between border-b border-separator px-4 py-2 lg:hidden">
        <Brand />
        <NotificationBell />
      </header>

      <main id="main" tabIndex={-1} className="mx-auto w-full max-w-4xl px-4 pb-28 pt-5 focus:outline-none sm:px-6 lg:pb-12">
        {children}
      </main>

      {/* iOS-style tab bar */}
      <nav
        aria-label="Sections"
        className="material fixed inset-x-0 bottom-0 z-30 border-t border-separator pb-[env(safe-area-inset-bottom,0px)] lg:hidden"
      >
        <ul className="mx-auto flex max-w-lg">
          {TAB_ITEMS.map(({ href, label, icon: Icon }) => {
            const active = mounted && isActive(pathname, href);
            return (
              <li key={href} className="flex-1">
                <Link
                  href={href}
                  aria-current={active ? "page" : undefined}
                  className={clsx(
                    "flex min-h-14 flex-col items-center justify-center gap-0.5 text-caption",
                    active ? "font-semibold text-blue" : "text-label-2",
                  )}
                >
                  <Icon aria-hidden="true" className="size-6" />
                  {label}
                </Link>
              </li>
            );
          })}
        </ul>
      </nav>
    </div>
  );
}
