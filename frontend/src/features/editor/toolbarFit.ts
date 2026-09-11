import { type RefObject, useLayoutEffect, useState } from "react";

/**
 * How much of the editor toolbar fits the pane it is in.
 *
 * The toolbar has more controls than a narrow pane can show at the 30px visual
 * size the editor contract pins, and shrinking them is not an option —
 * DESIGN.md requires a 44px target. So at the regular width the controls that do
 * not fit move into a "More actions" popover, worst-earned first
 * (docs/features/editor.md). At the compact width the bar scrolls horizontally
 * instead (`scrollable`), so nothing collapses — see `toolbarPlan`.
 *
 * Two things make this arithmetic rather than measurement: every control is
 * exactly 30px wide with a 2px gap, and every divider is exactly 1px with 4px
 * either side. The only thing that has to be measured is the *container*, and
 * DESIGN.md calls a component reflowing at its own width allowed and needing no
 * page breakpoint — the same reasoning `features/media/useVirtualGrid.ts`
 * already follows for its column count.
 *
 * A container query cannot express this, because the choice is not
 * presentational: a control that does not fit has to be rendered *inside the
 * popover instead*. Rendering it in both places and hiding one copy would put
 * two controls with the same accessible name in the accessibility tree.
 */

/** Groups that move into the More popover, in the order they give up the bar. */
export type ToolbarGroup =
  /** Outdent / Indent. Only exists while the caret is on a list line. */
  | "nesting"
  | "headings"
  | "history"
  | "ordered"
  | "blockquote"
  /** Underline and Strike. */
  | "emphasis"
  /** The Markdown-help control. The word count moved below the prose (T5). */
  | "reference";

/**
 * Kept on the bar longest first.
 *
 * Read as a claim about writing, not about layout: nesting is contextual, so at
 * the moment it exists at all it is the thing the writer is doing; structure
 * (headings) and safety (undo) outrank a second list style; the Markdown-help
 * control is a reference, not a writing action, so it is the first thing a
 * narrow bar gives up.
 *
 * Nesting being first means the caret entering a list line can push the
 * *lowest*-ranked group into the popover. That displacement is unavoidable — a
 * contextual control has to take its 64px from somewhere, and the alternatives
 * are worse: reserving the space permanently costs a real group at every width,
 * and ranking nesting last buries Outdent/Indent in the popover even on a
 * 1920px screen, where they are the only touch route to nesting.
 */
const KEEP_ORDER: readonly ToolbarGroup[] = [
  "nesting",
  "headings",
  "history",
  "ordered",
  "blockquote",
  "emphasis",
  "reference",
];

/** Border-box width each group adds, including the 2px flex gap before it. */
const GROUP_WIDTH: Record<ToolbarGroup, number> = {
  nesting: 64,
  headings: 96,
  history: 64,
  ordered: 32,
  blockquote: 32,
  emphasis: 64,
  // One 30px control (Markdown help) plus the 2px flex gap before it. The word
  // count that used to share this group is now a document-footer line below the
  // prose (docs/features/editor.md, editor-imp-v2 T5), so `reference` is a
  // single button and no longer the widest thing the bar can drop.
  reference: 32,
};

/**
 * The controls that never move — Bold, Italic, Bullet, Checklist, Link, and the
 * insert group that leads the bar (Add media + Moment details) — plus the
 * dividers between the bar's sections and the toolbar's own padding. (Padding
 * only: the measured width is `clientWidth`, which excludes borders.)
 *
 * The insert group's empty-entry "Write from a prompt" button is not counted
 * here: it is present only while the entry is still blank, so `toolbarPlan` adds
 * `PROMPT_CTA_WIDTH` for it on demand rather than baking it into the base.
 */
const BASE_WIDTH = 265;

/** The More control and the divider in front of it. */
const MORE_WIDTH = 43;

/**
 * The "Write from a prompt" button in the insert group. Budgeted like
 * `MORE_WIDTH` — the 30px control plus the divider-width of separation it needs
 * leading the formatting controls — not a bare 32px, so the arithmetic stays on
 * the safe side of the real rendered width. Shown only on a still-empty entry
 * (docs/features/prompts.md) and gone before any writing could crowd the bar, so
 * it never collapses: it is a width the planner reserves when told to, not a
 * `ToolbarGroup`.
 */
const PROMPT_CTA_WIDTH = 44;

export type ToolbarPlan = {
  /** Groups the bar has room for. Everything else is in the popover. */
  onBar: ReadonlySet<ToolbarGroup>;
  /** Whether a More control is needed at all. */
  needsMore: boolean;
};

/**
 * Which groups the bar can hold at `availableWidth` (its content-box width).
 *
 * An unmeasured width — before first paint, or in a test environment with no
 * layout engine — shows everything. That is the honest default: it is what the
 * writer sees at every width that can hold it, and nothing is hidden by a
 * measurement that never arrived.
 *
 * `scrollable` is the compact-width case: the bar is a single row that scrolls
 * horizontally (the standard mobile toolbar pattern), so nothing collapses into
 * the More popover — every group stays on the bar and the writer swipes to
 * reach it. The measured-collapse path below is only for the regular width,
 * where a horizontal scrollbar under a mouse is worse than a tidy More button.
 *
 * `hasPromptCta` reserves `PROMPT_CTA_WIDTH` for the insert group's empty-entry
 * "Write from a prompt" button: while it is shown the bar has that much less to
 * spend, so a width that fits everything without it can need the More popover
 * with it. It is gone once the writer types, so this only bites on a blank
 * entry in a narrow pane.
 */
export function toolbarPlan(
  availableWidth: number | null,
  {
    onListLine,
    scrollable = false,
    hasPromptCta = false,
  }: { onListLine: boolean; scrollable?: boolean; hasPromptCta?: boolean },
): ToolbarPlan {
  const groups = KEEP_ORDER.filter(
    (group) => group !== "nesting" || onListLine,
  );
  const everything = { onBar: new Set(groups), needsMore: false };
  if (scrollable || availableWidth === null || availableWidth <= 0) {
    return everything;
  }

  const fixed = BASE_WIDTH + (hasPromptCta ? PROMPT_CTA_WIDTH : 0);
  const whole = groups.reduce(
    (total, group) => total + GROUP_WIDTH[group],
    fixed,
  );
  if (whole <= availableWidth) return everything;

  // Stop at the first group that does not fit rather than skipping to a smaller
  // one further down: the bar's own order is fixed, so taking groups out of
  // sequence would make which controls are present unpredictable as the pane
  // resizes.
  const onBar = new Set<ToolbarGroup>();
  let used = fixed + MORE_WIDTH;
  for (const group of groups) {
    if (used + GROUP_WIDTH[group] > availableWidth) break;
    used += GROUP_WIDTH[group];
    onBar.add(group);
  }
  return { onBar, needsMore: true };
}

/**
 * The element's content-box inline size, or `null` while it cannot be measured.
 *
 * Measured in a layout effect so the first paint is already correct, then kept
 * current with a ResizeObserver: the editor pane changes width when the
 * navigation drawer opens and when the window is resized, neither of which is a
 * re-render of this component.
 */
export function useElementWidth(
  ref: RefObject<HTMLElement | null>,
): number | null {
  const [width, setWidth] = useState<number | null>(null);

  useLayoutEffect(() => {
    const node = ref.current;
    if (!node) return;
    // Only ever writes state when the number actually changed: this runs on
    // every frame while a window is being dragged.
    const measure = (next: number) =>
      setWidth((current) => (current === next ? current : next));
    // clientWidth includes padding, which the widths above already account for.
    measure(node.clientWidth);
    if (typeof ResizeObserver !== "function") return;
    const observer = new ResizeObserver((entries) => {
      const entry = entries[0];
      if (entry) measure(entry.target.clientWidth);
    });
    observer.observe(node);
    return () => observer.disconnect();
  }, [ref]);

  return width;
}
