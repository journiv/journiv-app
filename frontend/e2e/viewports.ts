/** The canonical viewports. DESIGN.md §20 requires 1440 / 1024 / 390 for manual
 *  review; these are the same three widths, so an E2E failure and a design
 *  review talk about the same layouts.
 *
 *  Each maps onto one of the three layout bands in DESIGN.md §9. Picking a width
 *  from this file rather than inventing one is what keeps "mobile" meaning the
 *  same thing in every spec.
 */
export const VIEWPORTS = {
  /** > 1100px — nav ∥ list ∥ page, all three panes persistent. */
  desktop: { width: 1440, height: 900 },
  /** 861–1100px — list ∥ page, with nav collapsed into the PageBar drawer. */
  tablet: { width: 1024, height: 768 },
  /** <= 860px — one pane per screen; browser history is the navigation. */
  mobile: { width: 390, height: 844 },
} as const;

export type ViewportName = keyof typeof VIEWPORTS;
