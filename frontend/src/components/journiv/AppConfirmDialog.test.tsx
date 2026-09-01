import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { setTestViewportWidth } from "../../test/viewport";
import { AppConfirmDialog } from "./AppConfirmDialog";

const COMPACT = 390;
const REGULAR = 1440;

function Harness(
  props: Partial<React.ComponentProps<typeof AppConfirmDialog>> = {},
) {
  return (
    <AppConfirmDialog
      open
      onOpenChange={() => {}}
      title="Delete entry?"
      description="This permanently deletes this entry."
      confirmLabel="Delete entry"
      destructive
      onConfirm={() => {}}
      {...props}
    />
  );
}

describe("AppConfirmDialog", () => {
  it.each([
    ["regular", REGULAR],
    ["compact", COMPACT],
  ])("exposes the title as the accessible name (%s)", async (_n, width) => {
    setTestViewportWidth(width);
    render(<Harness />);
    expect(
      await screen.findByRole(width === REGULAR ? "alertdialog" : "dialog", {
        name: "Delete entry?",
      }),
    ).toBeTruthy();
  });

  it("is a real alertdialog in the regular presentation", async () => {
    setTestViewportWidth(REGULAR);
    render(<Harness />);
    expect(await screen.findByRole("alertdialog")).toBeTruthy();
  });

  it("is a dialog, not an alertdialog, in the compact presentation", async () => {
    setTestViewportWidth(COMPACT);
    render(<Harness />);
    // Base UI's Drawer reads its role from the shared dialog store and never
    // becomes an alertdialog. This asserts the honest role rather than one the
    // primitive does not implement — see the note in AppConfirmDialog.tsx.
    expect(await screen.findByRole("dialog")).toBeTruthy();
    expect(screen.queryByRole("alertdialog")).toBeNull();
  });

  it.each([
    ["regular", REGULAR],
    ["compact", COMPACT],
  ])("cancel closes without confirming (%s)", async (_n, width) => {
    setTestViewportWidth(width);
    const onOpenChange = vi.fn();
    const onConfirm = vi.fn();
    render(<Harness onOpenChange={onOpenChange} onConfirm={onConfirm} />);
    await screen.findByRole("button", { name: "Cancel" });

    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));

    expect(onOpenChange).toHaveBeenCalledWith(false);
    expect(onConfirm).not.toHaveBeenCalled();
  });

  it.each([
    ["regular", REGULAR],
    ["compact", COMPACT],
  ])("confirm invokes onConfirm exactly once (%s)", async (_n, width) => {
    setTestViewportWidth(width);
    const onConfirm = vi.fn();
    render(<Harness onConfirm={onConfirm} />);
    await screen.findByRole("button", { name: "Delete entry" });

    await userEvent.click(screen.getByRole("button", { name: "Delete entry" }));

    expect(onConfirm).toHaveBeenCalledTimes(1);
  });

  it("suppresses a rejected confirmation and keeps the surface open", async () => {
    setTestViewportWidth(REGULAR);
    const onOpenChange = vi.fn();
    const onConfirm = vi.fn().mockRejectedValue(new Error("delete failed"));
    render(<Harness onOpenChange={onOpenChange} onConfirm={onConfirm} />);

    await userEvent.click(
      await screen.findByRole("button", { name: "Delete entry" }),
    );

    expect(onConfirm).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("alertdialog")).toBeTruthy();
    expect(onOpenChange).not.toHaveBeenCalled();
  });

  it.each([
    ["regular", REGULAR],
    ["compact", COMPACT],
  ])("destructive confirm is distinct from cancel (%s)", async (_n, width) => {
    setTestViewportWidth(width);
    render(<Harness />);
    const confirm = await screen.findByRole("button", {
      name: "Delete entry",
    });
    const cancel = screen.getByRole("button", { name: "Cancel" });

    // The design contract (§6): `danger` is tinted destructive text, never the
    // filled primary. Asserting the treatment, not a whole class string.
    expect(confirm.className).toContain("text-destructive");
    expect(cancel.className).not.toContain("text-destructive");
    expect(confirm.className).not.toContain("bg-primary");
  });

  it("uses the primary treatment when not destructive", async () => {
    setTestViewportWidth(REGULAR);
    render(<Harness destructive={false} confirmLabel="Save" />);
    const confirm = await screen.findByRole("button", { name: "Save" });
    expect(confirm.className).toContain("bg-primary");
  });

  it.each([
    ["regular", REGULAR],
    ["compact", COMPACT],
  ])("pending disables both actions (%s)", async (_n, width) => {
    setTestViewportWidth(width);
    render(<Harness pending />);
    await screen.findByRole("button", { name: /Delete entry/ });
    expect(
      screen
        .getByRole("button", { name: /Delete entry/ })
        .hasAttribute("disabled"),
    ).toBe(true);
    expect(
      screen.getByRole("button", { name: "Cancel" }).hasAttribute("disabled"),
    ).toBe(true);
  });

  it.each([
    ["regular", REGULAR],
    ["compact", COMPACT],
  ])("Escape cannot dismiss while pending (%s)", async (_n, width) => {
    setTestViewportWidth(width);
    const onOpenChange = vi.fn();
    render(<Harness pending onOpenChange={onOpenChange} />);
    await screen.findByRole("button", { name: "Cancel" });

    await userEvent.keyboard("{Escape}");

    expect(onOpenChange).not.toHaveBeenCalled();
  });

  it("Escape dismisses when idle", async () => {
    setTestViewportWidth(REGULAR);
    const onOpenChange = vi.fn();
    render(<Harness onOpenChange={onOpenChange} />);
    await screen.findByRole("alertdialog");

    await userEvent.keyboard("{Escape}");

    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it("renders supplied children, such as a failure notice", async () => {
    setTestViewportWidth(REGULAR);
    render(
      <Harness>
        <p role="alert">The entry couldn’t be deleted. Try again.</p>
      </Harness>,
    );
    expect(await screen.findByRole("alert")).toBeTruthy();
  });
});
