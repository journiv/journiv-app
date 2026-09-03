import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";
import { setTestViewportWidth } from "../../test/viewport";
import { AppAdaptiveDialog } from "./AppAdaptiveDialog";
import { Button } from "../ui/button";

/** DESIGN.md: <= 860px is compact, > 860px is regular. */
const COMPACT = 390;
const REGULAR = 1440;

function Harness({
  onOpenChange = () => {},
  ...props
}: Partial<React.ComponentProps<typeof AppAdaptiveDialog>>) {
  return (
    <AppAdaptiveDialog
      open
      onOpenChange={onOpenChange}
      title="Edit journal"
      description="Change this journal's details."
      footer={<Button variant="default">Save changes</Button>}
      {...props}
    >
      <label htmlFor="jv-title">Title</label>
      <input id="jv-title" />
    </AppAdaptiveDialog>
  );
}

describe("AppAdaptiveDialog", () => {
  it.each([
    ["regular", REGULAR],
    ["compact", COMPACT],
  ])("exposes the title as the accessible name (%s)", async (_name, width) => {
    setTestViewportWidth(width);
    render(<Harness />);
    expect(
      await screen.findByRole("dialog", { name: "Edit journal" }),
    ).toBeTruthy();
  });

  it.each([
    ["regular", REGULAR],
    ["compact", COMPACT],
  ])("renders children and footer (%s)", async (_name, width) => {
    setTestViewportWidth(width);
    render(<Harness />);
    await screen.findByRole("dialog");
    expect(screen.getByLabelText("Title")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Save changes" })).toBeTruthy();
  });

  it.each([
    ["regular", REGULAR],
    ["compact", COMPACT],
  ])("mounts exactly one interactive tree (%s)", async (_name, width) => {
    setTestViewportWidth(width);
    render(<Harness />);
    await screen.findByRole("dialog");
    // The whole point of picking a branch rather than hiding one: a duplicated
    // tree would give two dialogs, two "Title" fields and two Save buttons.
    expect(screen.getAllByRole("dialog")).toHaveLength(1);
    expect(screen.getAllByLabelText("Title")).toHaveLength(1);
    expect(
      screen.getAllByRole("button", { name: "Save changes" }),
    ).toHaveLength(1);
  });

  it("hides the title visually while keeping the accessible name", async () => {
    setTestViewportWidth(REGULAR);
    render(<Harness titleVisuallyHidden />);
    const dialog = await screen.findByRole("dialog", { name: "Edit journal" });
    expect(dialog.querySelector(".sr-only")?.textContent).toBe("Edit journal");
  });

  it.each([
    ["regular", REGULAR],
    ["compact", COMPACT],
  ])("Escape closes when dismissible (%s)", async (_name, width) => {
    setTestViewportWidth(width);
    const onOpenChange = vi.fn();
    render(<Harness onOpenChange={onOpenChange} />);
    await screen.findByRole("dialog");

    await userEvent.keyboard("{Escape}");

    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it.each([
    ["regular", REGULAR],
    ["compact", COMPACT],
  ])("Escape does not close when dismissible=false (%s)", async (_n, width) => {
    setTestViewportWidth(width);
    const onOpenChange = vi.fn();
    render(<Harness dismissible={false} onOpenChange={onOpenChange} />);
    await screen.findByRole("dialog");

    await userEvent.keyboard("{Escape}");

    expect(onOpenChange).not.toHaveBeenCalled();
    expect(screen.getByRole("dialog")).toBeTruthy();
  });

  it("omits the close button when not dismissible", async () => {
    setTestViewportWidth(REGULAR);
    render(<Harness dismissible={false} />);
    await screen.findByRole("dialog");
    expect(screen.queryByRole("button", { name: "Close" })).toBeNull();
  });

  it("keeps caller-owned state when the viewport crosses 860px", async () => {
    setTestViewportWidth(REGULAR);

    // The form value lives above the adaptive component, which is the contract
    // that makes a remount across the boundary survivable.
    function Owner() {
      const [value, setValue] = useState("");
      return (
        <AppAdaptiveDialog open onOpenChange={() => {}} title="Edit journal">
          <label htmlFor="owned">Title</label>
          <input
            id="owned"
            value={value}
            onChange={(event) => setValue(event.target.value)}
          />
        </AppAdaptiveDialog>
      );
    }
    render(<Owner />);
    await screen.findByRole("dialog");
    await userEvent.type(screen.getByLabelText("Title"), "Trips");
    expect((screen.getByLabelText("Title") as HTMLInputElement).value).toBe(
      "Trips",
    );

    act(() => setTestViewportWidth(COMPACT));

    await screen.findByRole("dialog");
    expect((screen.getByLabelText("Title") as HTMLInputElement).value).toBe(
      "Trips",
    );
    expect(screen.getAllByLabelText("Title")).toHaveLength(1);
  });
});
