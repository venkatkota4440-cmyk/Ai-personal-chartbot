import type { ChatMessage } from "@shared/types";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { MessageItem } from "@/components/chat/message-item";

const base: ChatMessage = {
  id: "m1",
  role: "assistant",
  content: "Here is a plan.",
  created_at: "2026-10-16T10:00:00Z",
  confidence: "low",
  human_review_note: null,
  used_memories: [],
  memory_ranking: "keyword",
  model: "mock-deterministic",
};

describe("MessageItem", () => {
  it("shows confidence, model, and that no memories were used", () => {
    render(<MessageItem message={base} />);
    expect(screen.getByText("Low confidence")).toBeInTheDocument();
    expect(screen.getByText("Model: mock-deterministic")).toBeInTheDocument();
    expect(screen.getByText("No memories used")).toBeInTheDocument();
  });

  it("discloses used memories, including deleted ones", () => {
    render(
      <MessageItem
        message={{
          ...base,
          used_memories: [
            { id: "a", content: "Prefers Python", status: "current" },
            { id: "b", content: null, status: "deleted" },
          ],
        }}
      />,
    );
    expect(screen.getByText("Used 2 approved memories")).toBeInTheDocument();
    expect(screen.getByText("Prefers Python")).toBeInTheDocument();
    expect(screen.getByText("Deleted memory")).toBeInTheDocument();
  });

  it("shows the human review note", () => {
    render(<MessageItem message={{ ...base, human_review_note: "Human review needed: financial." }} />);
    expect(screen.getByText("Human review needed: financial.")).toBeInTheDocument();
  });

  it("renders model output as text, never as HTML", () => {
    const { container } = render(<MessageItem message={{ ...base, content: "<img src=x onerror=alert(1)>" }} />);
    expect(container.querySelector("img")).toBeNull();
    expect(screen.getByText("<img src=x onerror=alert(1)>")).toBeInTheDocument();
  });

  it("hides memory disclosure when memory was off", () => {
    render(<MessageItem message={{ ...base, memory_ranking: null }} />);
    expect(screen.queryByText("No memories used")).toBeNull();
  });
});
