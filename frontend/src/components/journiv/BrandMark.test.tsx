import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { BrandMark } from "./BrandMark";

describe("BrandMark", () => {
  it("renders a decorative, non-themeable mark", () => {
    const { container } = render(<BrandMark />);
    const svg = container.querySelector("svg");
    expect(svg?.getAttribute("aria-hidden")).toBe("true");
    expect(svg?.getAttribute("role")).toBeNull();
    // The identity tile is fixed Journiv blue, never the --brand token, so it
    // must not follow a user's accent personalization (DESIGN.md).
    expect(container.innerHTML).toContain("#405DE6");
    expect(container.innerHTML).not.toContain("var(--brand)");
  });

  it("pairs the mark with the Journiv wordmark for its accessible name", () => {
    const { container, getByText } = render(<BrandMark wordmark />);
    expect(getByText("Journiv")).toBeTruthy();
    expect(container.querySelector(".jv-brand-lockup")).not.toBeNull();
  });

  it("sizes the tile from the size prop", () => {
    const { container } = render(<BrandMark size={40} />);
    const svg = container.querySelector("svg");
    expect(svg?.getAttribute("width")).toBe("40");
    expect(svg?.getAttribute("height")).toBe("40");
  });
});
