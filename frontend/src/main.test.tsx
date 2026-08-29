import { waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";

describe("frontend entry point", () => {
  it("renders the application", async () => {
    const root = document.createElement("div");
    root.id = "root";
    document.body.append(root);

    await import("./main");

    await waitFor(() => {
      expect(root.textContent).toContain("Journiv");
    });
  });
});
