"use client";

import type { Conversation } from "@shared/types";
import { clsx } from "clsx";
import { Plus } from "lucide-react";
import Link from "next/link";

import { Button } from "@/components/ui/button";

export function ConversationList({
  conversations,
  activeId,
  onNewChat,
  onNavigate,
}: {
  conversations: Conversation[];
  activeId: string | null;
  onNewChat: () => void;
  onNavigate?: () => void;
}) {
  return (
    <div className="flex flex-col gap-3">
      <Button variant="tinted" onClick={onNewChat} className="w-full">
        <Plus aria-hidden="true" className="size-4" />
        New chat
      </Button>
      {conversations.length === 0 ? (
        <p className="px-1 text-subhead text-label-2">No conversations yet.</p>
      ) : (
        <nav aria-label="Conversations">
          <ul className="flex flex-col gap-1">
            {conversations.map((c) => (
              <li key={c.id}>
                <Link
                  href={`/chat?c=${c.id}`}
                  onClick={onNavigate}
                  aria-current={c.id === activeId ? "page" : undefined}
                  className={clsx(
                    "flex min-h-11 items-center rounded-lg px-3 text-subhead",
                    c.id === activeId ? "bg-blue-tint text-label" : "text-label-2 hover:bg-surface-2 hover:text-label",
                  )}
                >
                  <span className="truncate">{c.title}</span>
                </Link>
              </li>
            ))}
          </ul>
        </nav>
      )}
    </div>
  );
}
