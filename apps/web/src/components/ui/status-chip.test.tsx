import type { RunStatus } from "@shared/types";
import { cleanup, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ApprovalChip, RiskChip, StatusChip } from "@/components/ui/status-chip";

const ALL: RunStatus[] = [
  "queued",
  "running",
  "awaiting_approval",
  "succeeded",
  "partially_succeeded",
  "failed",
  "cancelled",
];

describe("StatusChip", () => {
  it.each(ALL)("renders a text label for %s (not colour alone)", (status) => {
    render(<StatusChip status={status} />);
    expect(screen.getByText(/./)).toHaveTextContent(/\w+/);
  });

  it("labels a run that needs approval in plain words", () => {
    render(<StatusChip status="awaiting_approval" />);
    expect(screen.getByText("Needs approval")).toBeInTheDocument();
  });

  it("spells out risk and approval states too", () => {
    render(<RiskChip risk="high" />);
    expect(screen.getByText("Needs approval")).toBeInTheDocument();
    cleanup();
    render(<ApprovalChip status="consumed" />);
    expect(screen.getByText("Done once")).toBeInTheDocument();
  });
});
