import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { HelpPage } from "./HelpPage";

describe("HelpPage", () => {
  it("offers the temporary legacy interface without making it primary", () => {
    render(<HelpPage />);

    const legacy = screen.getByRole("link", { name: /use legacy interface/i });
    expect(legacy.getAttribute("href")).toBe("/legacy/");
    expect(legacy.getAttribute("target")).toBeNull();
  });
});
