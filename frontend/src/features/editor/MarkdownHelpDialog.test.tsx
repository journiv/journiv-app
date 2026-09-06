import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { setTestViewportWidth } from "../../test/viewport";
import { MarkdownHelpDialog } from "./MarkdownHelpDialog";

describe("MarkdownHelpDialog", () => {
  it.each([
    ["regular", 1440],
    ["compact", 390],
  ])("lists the supported shorthand (%s)", async (_name, width) => {
    setTestViewportWidth(width);
    render(<MarkdownHelpDialog open onOpenChange={() => {}} />);

    const dialog = await screen.findByRole("dialog", {
      name: "Markdown shortcuts",
    });
    for (const syntax of [
      "# ",
      "- ",
      "1. ",
      "> ",
      "**bold**",
      "[text](https://…)",
    ]) {
      expect(dialog.textContent).toContain(syntax);
    }
  });

  it("closes on Escape", async () => {
    setTestViewportWidth(1440);
    const onOpenChange = vi.fn();
    render(<MarkdownHelpDialog open onOpenChange={onOpenChange} />);
    await screen.findByRole("dialog");

    await userEvent.keyboard("{Escape}");
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it("renders nothing while closed", () => {
    render(<MarkdownHelpDialog open={false} onOpenChange={() => {}} />);
    expect(screen.queryByRole("dialog")).toBeNull();
  });
});
