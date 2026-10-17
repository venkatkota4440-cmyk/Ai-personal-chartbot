import type { ReactNode } from "react";

import { AppShell } from "@/components/shell/app-shell";
import { SessionProvider } from "@/lib/session";

export default function AuthenticatedLayout({ children }: { children: ReactNode }) {
  return (
    <SessionProvider>
      <AppShell>{children}</AppShell>
    </SessionProvider>
  );
}
