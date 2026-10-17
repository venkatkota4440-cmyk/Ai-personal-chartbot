import type { Memory } from "@shared/types";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ProposalCard } from "@/components/chat/proposal-card";

const memory: Memory = {
  id: "mem-1",
  content: "Prefers Python examples",
  source: "chat",
  status: "proposed",
  conversation_id: "c1",
  created_at: "2026-10-16T10:00:00Z",
  updated_at: "2026-10-16T10:00:00Z",
};

describe("ProposalCard", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("approves via PATCH and reports the updated memory", async () => {
    document.cookie = "paa_csrf=n.s";
    const fetchMock = vi.fn<typeof fetch>().mockResolvedValue(
      new Response(JSON.stringify({ ...memory, status: "approved" }), { status: 200 }),
    );
    vi.stubGlobal("fetch", fetchMock);
    const onDecided = vi.fn();
    render(<ProposalCard memory={memory} onDecided={onDecided} />);

    await userEvent.click(screen.getByRole("button", { name: "Approve memory: Prefers Python examples" }));

    expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/memories/mem-1");
    expect(JSON.parse(String(fetchMock.mock.calls[0]?.[1]?.body))).toEqual({ status: "approved" });
    expect(onDecided).toHaveBeenCalledWith(expect.objectContaining({ status: "approved" }));
  });

  it("shows an error instead of failing silently", async () => {
    document.cookie = "paa_csrf=n.s";
    vi.stubGlobal("fetch", vi.fn<typeof fetch>().mockRejectedValue(new TypeError("offline")));
    render(<ProposalCard memory={memory} onDecided={vi.fn()} />);
    await userEvent.click(screen.getByRole("button", { name: /Reject memory/ }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Could not reach the server");
  });
});
