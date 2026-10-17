import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { TextField } from "@/components/ui/field";

describe("TextField", () => {
  it("associates the label, hint, and error with the input", () => {
    render(<TextField label="Email" hint="We never share it" error="Enter a valid email address" />);
    const input = screen.getByLabelText("Email");
    expect(input).toHaveAttribute("aria-invalid", "true");
    expect(input).toHaveAccessibleDescription("We never share it Enter a valid email address");
  });
});
