import { describe, expect, it } from "vitest";
import { type ToolbarGroup, toolbarPlan } from "./toolbarFit";

const plan = (width: number | null, onListLine = false) =>
  toolbarPlan(width, { onListLine });

const onBar = (width: number | null, onListLine = false): ToolbarGroup[] =>
  [...plan(width, onListLine).onBar].sort();

describe("toolbarPlan", () => {
  it("shows every group when the width is not measurable", () => {
    // Before first paint, and in any environment with no layout engine. Hiding
    // controls because a measurement never arrived would be the worse failure.
    expect(plan(null).needsMore).toBe(false);
    expect(onBar(null)).toEqual([
      "blockquote",
      "emphasis",
      "headings",
      "history",
      "ordered",
      "reference",
    ]);
    expect(plan(0).needsMore).toBe(false);
  });

  it("needs no More control once the whole bar fits", () => {
    const wide = plan(900);
    expect(wide.needsMore).toBe(false);
    expect(wide.onBar.has("reference")).toBe(true);
  });

  it("fits the whole bar in the three-pane editor pane once the count is gone", () => {
    // The width of the editor pane at 1440 in Journiv's three-pane layout. With
    // the word count moved below the prose (T5), the Markdown-help control is
    // the only thing left in `reference` and the entire formatting set — help
    // included — now fits inline with no More control at all.
    const pane = plan(616);
    expect(pane.needsMore).toBe(false);
    expect(pane.onBar.has("reference")).toBe(true);
  });

  it("reserves width for the still-empty entry's prompt button", () => {
    // "Write from a prompt" leads the insert group only while the entry is
    // blank (docs/features/prompts.md). While it is there the bar has 32px less
    // to spend, so a width that fits everything without it can need the More
    // popover with it.
    expect(toolbarPlan(600, { onListLine: false }).needsMore).toBe(false);
    expect(
      toolbarPlan(600, { onListLine: false, hasPromptCta: true }).needsMore,
    ).toBe(true);
    // A wide bar still shows every group with the button present.
    const wide = toolbarPlan(900, { onListLine: false, hasPromptCta: true });
    expect(wide.needsMore).toBe(false);
    expect(wide.onBar.has("reference")).toBe(true);
  });

  it("gives up the Markdown-help control before the groups ranked above it", () => {
    // `reference` is kept last, so a bar too narrow to hold everything sheds it
    // first. It goes together with `emphasis` at the boundary: adding the More
    // control costs 43px, more than the 32px `reference` frees on its own.
    const pane = plan(560);
    expect(pane.needsMore).toBe(true);
    expect(pane.onBar.has("reference")).toBe(false);
    for (const kept of [
      "headings",
      "history",
      "ordered",
      "blockquote",
    ] as const) {
      expect(pane.onBar.has(kept), kept).toBe(true);
    }
  });

  it("keeps structure and history on a phone-width bar before list styling", () => {
    // 390px viewport: a 16px gutter each side, so the bar is 358px wide.
    const phone = plan(358);
    expect(phone.needsMore).toBe(true);
    expect([...phone.onBar]).toEqual([]);

    // A little more room buys back headings first, then undo/redo.
    expect(onBar(410)).toEqual(["headings"]);
    expect(onBar(480)).toEqual(["headings", "history"]);
  });

  it("never takes a later group out of order when an earlier one does not fit", () => {
    // 410px holds headings (96) with 6px to spare — enough for `ordered` (32)
    // only if the bar were allowed to reorder itself, which it is not: which
    // controls are on the bar must not shuffle as the pane is dragged.
    expect(onBar(440)).toEqual(["headings"]);
  });

  it("keeps list nesting on the bar wherever there is room for it", () => {
    expect(plan(900, false).onBar.has("nesting")).toBe(false);
    expect(plan(900, true).onBar.has("nesting")).toBe(true);
    // The editor pane at 1440 in the three-pane layout. Outdent/Indent must be
    // on the bar here: a desktop writer should not have to open a popover to
    // nest a list item.
    expect(plan(616, true).onBar.has("nesting")).toBe(true);
    // A phone-width bar has room for nothing beyond the fixed set, so
    // Outdent/Indent are one tap away in the More popover instead.
    expect(onBar(358, true)).toEqual([]);
  });

  it("displaces only the lowest-ranked group when the caret enters a list", () => {
    // A contextual control has to take its width from somewhere. What it must
    // not do is take it from the middle: everything ranked above nesting stays
    // exactly where it was.
    let checked = 0;
    for (let width = 300; width <= 900; width += 4) {
      const off = plan(width, false).onBar;
      const on = plan(width, true).onBar;
      if (!on.has("nesting")) continue; // nesting did not fit; nothing moved
      // Every group still on the bar was already there, and the ones that left
      // are a suffix of the keep order — never a control from the middle.
      for (const group of on) {
        if (group === "nesting") continue;
        expect(off.has(group), `${width}px kept ${group}`).toBe(true);
      }
      checked += 1;
    }
    expect(checked).toBeGreaterThan(80);
  });

  it("keeps every group on the bar when it is scrollable, at any width", () => {
    // The compact width: the bar is one horizontally scrolling row, so nothing
    // collapses however narrow the phone is.
    const phone = toolbarPlan(320, { onListLine: false, scrollable: true });
    expect(phone.needsMore).toBe(false);
    expect([...phone.onBar].sort()).toEqual([
      "blockquote",
      "emphasis",
      "headings",
      "history",
      "ordered",
      "reference",
    ]);
    // And nesting joins them once the caret is on a list line.
    expect(
      toolbarPlan(320, { onListLine: true, scrollable: true }).onBar.has(
        "nesting",
      ),
    ).toBe(true);
  });

  it("widens monotonically — a wider bar never shows fewer groups", () => {
    let previous = 0;
    for (let width = 300; width <= 900; width += 8) {
      const count = plan(width).onBar.size;
      expect(count, `${width}px`).toBeGreaterThanOrEqual(previous);
      previous = count;
    }
  });
});
