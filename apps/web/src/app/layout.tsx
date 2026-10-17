import type { Metadata, Viewport } from "next";
import type { ReactNode } from "react";

import "./globals.css";

export const metadata: Metadata = {
  title: { default: "Personal Agent", template: "%s · Personal Agent" },
  description: "Your personal AI assistant for tasks, projects, and safe automations.",
  robots: { index: false, follow: false },
  appleWebApp: { capable: true, title: "Personal Agent", statusBarStyle: "default" },
};

export const viewport: Viewport = {
  // Matches the system background in each appearance, so the browser chrome blends in.
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#f2f2f7" },
    { media: "(prefers-color-scheme: dark)", color: "#000000" },
  ],
  viewportFit: "cover",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-dvh antialiased">{children}</body>
    </html>
  );
}
