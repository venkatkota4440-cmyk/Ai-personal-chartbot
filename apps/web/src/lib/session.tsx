"use client";

import type { User } from "@shared/types";
import { usePathname, useRouter } from "next/navigation";
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

import { api, ApiError } from "@/lib/api";

type SessionState =
  | { status: "loading" }
  | { status: "authenticated"; user: User }
  | { status: "error"; error: ApiError };

interface SessionContextValue {
  state: SessionState;
  reload: () => void;
  setUser: (user: User) => void;
  signOut: () => Promise<void>;
}

const SessionContext = createContext<SessionContextValue | null>(null);

export function SessionProvider({ children }: { children: ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const [state, setState] = useState<SessionState>({ status: "loading" });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    api<User>("/api/auth/me", { signal: controller.signal })
      .then((user) => setState({ status: "authenticated", user }))
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        if (error instanceof ApiError && error.status === 401) {
          router.replace(`/login?next=${encodeURIComponent(pathname)}`);
          return;
        }
        setState({
          status: "error",
          error: error instanceof ApiError ? error : new ApiError(0, "internal_error", "Unexpected error"),
        });
      });
    return () => controller.abort();
    // pathname is intentionally excluded: the session does not need re-checking on every navigation.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [attempt, router]);

  const reload = useCallback(() => {
    setState({ status: "loading" });
    setAttempt((n) => n + 1);
  }, []);

  const setUser = useCallback((user: User) => setState({ status: "authenticated", user }), []);

  const signOut = useCallback(async () => {
    await api<void>("/api/auth/logout", { method: "POST" });
    router.replace("/login");
    router.refresh();
  }, [router]);

  const value = useMemo(() => ({ state, reload, setUser, signOut }), [state, reload, setUser, signOut]);
  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession(): SessionContextValue {
  const context = useContext(SessionContext);
  if (!context) throw new Error("useSession must be used inside SessionProvider");
  return context;
}

/** For components that only render once the shell has confirmed the session. */
export function useCurrentUser(): User {
  const { state } = useSession();
  if (state.status !== "authenticated") throw new Error("useCurrentUser called before authentication");
  return state.user;
}
