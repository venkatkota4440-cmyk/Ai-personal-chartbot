"use client";

import * as Dialog from "@radix-ui/react-dialog";
import type { ChatResponse, Conversation, ConversationDetail, Memory } from "@shared/types";
import { BookMarked, History, Send, Trash2, X } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from "react";

import { ConversationList } from "@/components/chat/conversation-list";
import { MessageItem } from "@/components/chat/message-item";
import { ProposalCard } from "@/components/chat/proposal-card";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { EmptyState, ErrorState, LoadingState, Notice } from "@/components/ui/states";
import { SwitchField } from "@/components/ui/switch";
import { api, ApiError } from "@/lib/api";
import { messageWasSaved, toApiError } from "@/lib/errors";

const MAX_CHARS = 8000;

interface Seed {
  detail: ConversationDetail;
  proposals: Memory[];
}

type ListState = { status: "loading" } | { status: "ready"; items: Conversation[] } | { status: "error"; error: ApiError };

export function ChatWorkspace() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const activeId = searchParams.get("c");
  const [list, setList] = useState<ListState>({ status: "loading" });
  const [listVersion, setListVersion] = useState(0);
  const [historyOpen, setHistoryOpen] = useState(false);
  // Hands the first reply of a brand-new chat to the thread so it does not flash a reload.
  const [createdSeed, setCreatedSeed] = useState<Seed | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    api<Conversation[]>("/api/conversations", { signal: controller.signal })
      .then((items) => setList({ status: "ready", items }))
      .catch((e: unknown) => {
        if (!controller.signal.aborted) setList({ status: "error", error: toApiError(e) });
      });
    return () => controller.abort();
  }, [listVersion]);

  const refreshList = useCallback(() => setListVersion((n) => n + 1), []);

  const openConversation = useCallback(
    (id: string | null) => {
      router.replace(id ? `/chat?c=${id}` : "/chat");
      refreshList();
    },
    [router, refreshList],
  );

  const onCreated = useCallback(
    (seed: Seed) => {
      setCreatedSeed(seed);
      openConversation(seed.detail.id);
    },
    [openConversation],
  );

  const seed = createdSeed && createdSeed.detail.id === activeId ? createdSeed : null;
  const listPanel =
    list.status === "loading" ? (
      <LoadingState label="Loading conversations…" />
    ) : list.status === "error" ? (
      <ErrorState error={list.error} onRetry={refreshList} />
    ) : (
      <ConversationList
        conversations={list.items}
        activeId={activeId}
        onNewChat={() => {
          setHistoryOpen(false);
          openConversation(null);
        }}
        onNavigate={() => setHistoryOpen(false)}
      />
    );

  return (
    <div className="grid gap-6 lg:grid-cols-[16rem_1fr]">
      <aside className="hidden lg:block" aria-label="Chat history">
        {listPanel}
      </aside>

      <section aria-label="Conversation" className="flex min-w-0 flex-col">
        <div className="mb-4 flex items-center justify-between gap-2 lg:hidden">
          <Dialog.Root open={historyOpen} onOpenChange={setHistoryOpen}>
            <Dialog.Trigger asChild>
              <Button variant="tinted">
                <History aria-hidden="true" className="size-4" />
                Conversations
              </Button>
            </Dialog.Trigger>
            <Dialog.Portal>
              <Dialog.Overlay className="fixed inset-0 z-40 bg-black/60" />
              <Dialog.Content className="fixed inset-y-0 left-0 z-50 flex w-80 max-w-[85vw] flex-col gap-4 overflow-y-auto border-r border-separator bg-surface p-4">
                <div className="flex items-center justify-between">
                  <Dialog.Title className="font-semibold">Conversations</Dialog.Title>
                  <Dialog.Close asChild>
                    <Button variant="plain" aria-label="Close conversations" className="px-3">
                      <X aria-hidden="true" className="size-5" />
                    </Button>
                  </Dialog.Close>
                </div>
                <Dialog.Description className="sr-only">Open a previous conversation or start a new one</Dialog.Description>
                {listPanel}
              </Dialog.Content>
            </Dialog.Portal>
          </Dialog.Root>
          <Link href="/memories" className="inline-flex min-h-11 items-center gap-2 text-subhead font-semibold text-blue">
            <BookMarked aria-hidden="true" className="size-4" />
            Memory
          </Link>
        </div>

        <ChatThread
          key={activeId ?? "new"}
          conversationId={activeId}
          seed={seed}
          onCreated={onCreated}
          onActivity={refreshList}
          onOpen={openConversation}
          onDeleted={() => openConversation(null)}
        />
      </section>
    </div>
  );
}

type ThreadState =
  | { status: "loading" }
  | { status: "ready"; detail: ConversationDetail | null }
  | { status: "error"; error: ApiError };

function ChatThread({
  conversationId,
  seed,
  onCreated,
  onActivity,
  onOpen,
  onDeleted,
}: {
  conversationId: string | null;
  seed: Seed | null;
  onCreated: (seed: Seed) => void;
  onActivity: () => void;
  onOpen: (id: string | null) => void;
  onDeleted: () => void;
}) {
  const [thread, setThread] = useState<ThreadState>(() =>
    seed ? { status: "ready", detail: seed.detail } : conversationId ? { status: "loading" } : { status: "ready", detail: null },
  );
  const [proposals, setProposals] = useState<Memory[]>(seed?.proposals ?? []);
  const [attempt, setAttempt] = useState(0);
  const [newChatMemory, setNewChatMemory] = useState(true);
  const [draft, setDraft] = useState("");
  const [pendingText, setPendingText] = useState<string | null>(null);
  const [sendError, setSendError] = useState<ApiError | null>(null);
  const [toggleError, setToggleError] = useState<string | null>(null);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!conversationId || (seed && attempt === 0)) return;
    const controller = new AbortController();
    Promise.all([
      api<ConversationDetail>(`/api/conversations/${conversationId}`, { signal: controller.signal }),
      api<Memory[]>("/api/memories?status=proposed", { signal: controller.signal }),
    ])
      .then(([detail, pending]) => {
        setThread({ status: "ready", detail });
        setProposals(pending.filter((m) => m.conversation_id === conversationId));
      })
      .catch((e: unknown) => {
        if (!controller.signal.aborted) setThread({ status: "error", error: toApiError(e) });
      });
    return () => controller.abort();
    // `seed` only matters for the first render of a new chat.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [conversationId, attempt]);

  const messages = thread.status === "ready" ? (thread.detail?.messages ?? []) : [];
  const messageCount = messages.length;

  useEffect(() => {
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    endRef.current?.scrollIntoView({ block: "end", behavior: reduce ? "auto" : "smooth" });
  }, [messageCount, pendingText, proposals.length]);

  if (thread.status === "loading") return <LoadingState label="Loading conversation…" />;
  if (thread.status === "error")
    return (
      <ErrorState
        error={thread.error}
        onRetry={() => {
          setThread({ status: "loading" });
          setAttempt((n) => n + 1);
        }}
      />
    );

  const detail = thread.detail;
  const memoryEnabled = detail ? detail.memory_enabled : newChatMemory;
  const sending = pendingText !== null;

  const setMemory = async (enabled: boolean) => {
    setToggleError(null);
    if (!detail) {
      setNewChatMemory(enabled);
      return;
    }
    try {
      const updated = await api<Conversation>(`/api/conversations/${detail.id}`, {
        method: "PATCH",
        body: { memory_enabled: enabled },
      });
      setThread({ status: "ready", detail: { ...detail, ...updated } });
    } catch (e) {
      setToggleError(toApiError(e).message);
    }
  };

  const send = async () => {
    const text = draft.trim();
    if (!text || sending) return;
    setSendError(null);
    setPendingText(text);
    setDraft("");
    try {
      const response = await api<ChatResponse>("/api/chat", {
        method: "POST",
        body: detail ? { message: text, conversation_id: detail.id } : { message: text, memory_enabled: newChatMemory },
      });
      const nextDetail: ConversationDetail = {
        ...response.conversation,
        messages: [...(detail?.messages ?? []), response.user_message, response.assistant_message],
      };
      if (!detail) {
        onCreated({ detail: nextDetail, proposals: response.proposed_memories });
        return;
      }
      setThread({ status: "ready", detail: nextDetail });
      setProposals((current) => [...current, ...response.proposed_memories]);
      onActivity();
    } catch (e) {
      const error = toApiError(e);
      setSendError(error);
      if (!messageWasSaved(error)) {
        setDraft(text); // not stored on the server, so give the text back
      } else if (detail) {
        setAttempt((n) => n + 1); // reload to show the saved message
      } else {
        // The server created the conversation before the AI failed; open the newest one.
        const latest = await api<Conversation[]>("/api/conversations?limit=1").catch(() => []);
        if (latest[0]) onOpen(latest[0].id);
      }
    } finally {
      setPendingText(null);
    }
  };

  const onSubmit = (event: FormEvent) => {
    event.preventDefault();
    void send();
  };

  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      void send();
    }
  };

  return (
    <div className="flex flex-col gap-4">
      <header className="flex flex-col gap-3 border-b border-separator pb-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0">
          <h1 className="truncate text-title2 font-semibold tracking-tight sm:text-2xl">{detail ? detail.title : "New chat"}</h1>
          <p className="text-subhead text-label-2">
            Answers may be wrong. The assistant states its confidence and never takes actions from chat.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <div className="min-w-56">
            <SwitchField
              label="Use memory in this chat"
              description={memoryEnabled ? "Reads approved memories; may suggest new ones" : "Memory is off: nothing read or suggested"}
              checked={memoryEnabled}
              onCheckedChange={(v) => void setMemory(v)}
            />
          </div>
          {detail && (
            <ConfirmDialog
              trigger={
                <Button variant="plain" aria-label="Delete this conversation" className="px-3">
                  <Trash2 aria-hidden="true" className="size-5" />
                </Button>
              }
              title="Delete this conversation?"
              description="All of its messages are permanently deleted. Approved memories are kept."
              confirmLabel="Delete conversation"
              onConfirm={async () => {
                await api<void>(`/api/conversations/${detail.id}`, { method: "DELETE" });
                onDeleted();
              }}
            />
          )}
        </div>
      </header>
      {toggleError && <Notice tone="error">{toggleError}</Notice>}

      <div role="log" aria-live="polite" aria-label="Messages" className="flex min-h-64 flex-col gap-5">
        {messages.length === 0 && !sending && (
          <EmptyState
            title="Start a conversation"
            description="Ask a question, plan your day, or say “remember that…” to suggest a memory for your approval."
          />
        )}
        {messages.map((m) => (
          <MessageItem key={m.id} message={m} />
        ))}
        {pendingText !== null && (
          <>
            <MessageItem
              message={{
                id: "pending",
                role: "user",
                content: pendingText,
                created_at: new Date().toISOString(),
                confidence: null,
                human_review_note: null,
                used_memories: [],
                memory_ranking: null,
                model: null,
              }}
            />
            <LoadingState label="Assistant is replying…" />
          </>
        )}
        {proposals
          .filter((p) => p.status === "proposed")
          .map((p) => (
            <ProposalCard
              key={p.id}
              memory={p}
              onDecided={(updated) => setProposals((current) => current.map((c) => (c.id === updated.id ? updated : c)))}
            />
          ))}
      </div>

      {sendError && (
        <Notice tone="error">
          {sendError.message}
          {messageWasSaved(sendError) ? " Your message was saved; you can send it again later." : ""}
        </Notice>
      )}

      <form onSubmit={onSubmit} className="sticky bottom-0 flex flex-col gap-2 border-t border-separator bg-bg pb-2 pt-3">
        <label htmlFor="chat-input" className="sr-only">
          Message
        </label>
        <textarea
          id="chat-input"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={onKeyDown}
          maxLength={MAX_CHARS}
          rows={3}
          placeholder="Message your assistant… (Enter to send, Shift+Enter for a new line)"
          aria-describedby="chat-input-count"
          className="w-full resize-y rounded-xl border border-separator bg-surface px-4 py-3 text-body text-label placeholder:text-label-3 focus-visible:border-blue"
        />
        <div className="flex items-center justify-between gap-3">
          <span id="chat-input-count" className="text-footnote text-label-2">
            {draft.length}/{MAX_CHARS}
          </span>
          <div className="flex items-center gap-3">
            <Link href="/memories" className="hidden min-h-11 items-center gap-2 text-subhead font-semibold text-blue lg:inline-flex">
              <BookMarked aria-hidden="true" className="size-4" />
              Manage memory
            </Link>
            <Button type="submit" loading={sending} disabled={!draft.trim()}>
              {!sending && <Send aria-hidden="true" className="size-4" />}
              Send
            </Button>
          </div>
        </div>
      </form>
      {/* Scroll target sits below the sticky composer so the newest message and suggestions are never hidden by it. */}
      <div ref={endRef} />
    </div>
  );
}
