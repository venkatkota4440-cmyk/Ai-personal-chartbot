import type { Metadata } from "next";
import { Suspense } from "react";

import { ChatWorkspace } from "@/components/chat/chat-workspace";
import { LoadingState } from "@/components/ui/states";

export const metadata: Metadata = { title: "Chat" };

export default function ChatPage() {
  return (
    <Suspense fallback={<LoadingState label="Loading chat…" />}>
      <ChatWorkspace />
    </Suspense>
  );
}
