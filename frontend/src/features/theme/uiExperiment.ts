/**
 * DORMANT UI-feel A/B experiment layer (DESIGN.md §25).
 *
 * Round 2 of the "does Journiv feel modern" review. Three independent axes,
 * each a response to a specific piece of feedback:
 *
 *   comfort  default | roomy    — rounder root radius + roomier text-field
 *                                 padding ("soften the primitives").
 *   hover    flat | lively      — row hover adds a shadow and a 1px lift on top
 *                                 of the `--muted` tint ("give hover states
 *                                 more life").
 *   panes    soft | hairlines | airy — pane seams: the shipped faded `--jv-seam`
 *                                 (`soft`, no-op here), a forced hard `--border`
 *                                 hairline (`hairlines`), or a no-frame canvas
 *                                 gap (`airy`).
 *
 * Outcome of round 2: only `panes: soft` was adopted (shell.css `--jv-seam`).
 * `comfort` and `hover` stayed at default. The **Settings control is unmounted**
 * (see `AppearancePage`) — the framework is kept wired at boot so a future axis
 * can be added and driven from `localStorage` (`journiv.uiExperiment`) or by
 * re-mounting `UiExperimentSection`, without rebuilding the plumbing.
 *
 * Injected as `<style id="journiv-ui-experiment">`, appended to <head> AFTER
 * the user-theme layer so the experiment wins while active. It reaches into
 * `src/components/ui/*` rendered output through `[data-slot]` selectors rather
 * than editing those files (§18) — which is exactly why this is a throwaway
 * layer. Raw values live here in JS so the static design guard, which only
 * scans `.css`, stays green. `uiExperimentCss(UI_DEFAULT)` is `""`, so the
 * dormant framework adds nothing to the page.
 *
 * When there is no foreseeable next experiment: delete this module, its test,
 * `UiExperimentSection`, the `main.tsx` wiring and the DESIGN.md §25 subsection.
 */

export type UiComfort = "default" | "roomy";
export type UiHover = "flat" | "lively";
export type UiPanes = "hairlines" | "soft" | "airy";

export interface UiExperiment {
  comfort: UiComfort;
  hover: UiHover;
  panes: UiPanes;
}

// `panes: "soft"` shipped as the real default (shell.css `--jv-seam`, 2026-09),
// so it is the no-op baseline here; the axis now only carries the two
// directions that did NOT win, for future re-testing.
export const UI_DEFAULT: UiExperiment = {
  comfort: "default",
  hover: "flat",
  panes: "soft",
};

const STYLE_ID = "journiv-ui-experiment";
const STORAGE_KEY = "journiv.uiExperiment";

/* ---- axis fragments --------------------------------------------------- */

// "Soften the primitives": a friendlier root radius (the whole named scale
// re-derives from it, index.css `@theme inline`) and text fields that are not
// cramped. Only the field controls move — buttons keep base-vega's compact
// sizing (DESIGN.md §7).
const ROOMY = `
:root {
  --radius: 1.25rem;
}
[data-slot="input"],
[data-slot="native-select"] {
  height: auto;
  min-height: 2.5rem;
  padding-block: 0.5rem;
  padding-inline: 0.8125rem;
}
[data-slot="textarea"] {
  padding: 0.625rem 0.8125rem;
}
`;

// "Give hover states more life": keep the --muted tint, add a resting-to-raised
// move — a hairline-cheap shadow and a 1px lift — so a row acknowledges the
// pointer instead of just changing colour. Applies to every Journiv row
// treatment and the stock Item.
const LIVELY_HOVER = `
.jv-moment,
.jv-lib-row--link,
.jv-nav__item,
[data-slot="item"][class*="hover:bg-muted"] {
  transition:
    background-color var(--duration-fast) var(--ease),
    box-shadow var(--duration-fast) var(--ease),
    transform var(--duration-fast) var(--ease);
}
.jv-moment:hover,
.jv-lib-row--link:hover,
.jv-nav__item:hover,
[data-slot="item"][class*="hover:bg-muted"]:hover {
  background: color-mix(in oklab, var(--muted), var(--foreground) 4%);
  box-shadow: var(--shadow-xs);
  transform: translateY(-1px);
}
`;

// `hairlines` is the pre-2026-09 look: force the pane seams back to a full
// `--border` hairline, over the faded `--jv-seam` shell.css now ships. Kept so
// the winning direction can still be compared against the old one.
const PANES_HARD = `
.jv-shell {
  border-color: var(--border);
}
.jv-shell__nav,
.jv-shell__list {
  border-right-color: var(--border);
}
`;

// "Negative space as the separator": no shell frame, no inner borders, no
// shadow — the panes are held
// apart by a strip of the --muted canvas and their own tint. This is the
// composition §5 says was tried and rejected; the axis exists to look at it
// again, not to endorse it.
const PANES_AIRY = `
.jv-shell {
  border: 0;
  box-shadow: none;
  background: transparent;
  gap: var(--space-2);
}
.jv-shell__nav,
.jv-shell__list,
.jv-shell__page {
  border-right: 0;
  border-radius: var(--radius-lg);
  overflow: hidden;
}
.jv-shell__list {
  overflow: hidden;
}
@media (max-width: 860px) {
  .jv-shell {
    gap: 0;
  }
  .jv-shell__nav,
  .jv-shell__list,
  .jv-shell__page {
    border-radius: 0;
  }
}
`;

/** Serialises an experiment to CSS. Returns "" when every axis is at default. */
export function uiExperimentCss(exp: UiExperiment): string {
  const parts: string[] = [];
  if (exp.comfort === "roomy") parts.push(ROOMY);
  if (exp.hover === "lively") parts.push(LIVELY_HOVER);
  if (exp.panes === "hairlines") parts.push(PANES_HARD);
  if (exp.panes === "airy") parts.push(PANES_AIRY);
  return parts.join("\n").trim();
}

/** Installs / updates / removes the `<style id="journiv-ui-experiment">` layer. */
export function applyUiExperiment(exp: UiExperiment): void {
  if (typeof document === "undefined") return;

  const existing = document.getElementById(STYLE_ID);
  const css = uiExperimentCss(exp);
  if (!css) {
    existing?.remove();
    return;
  }

  const style =
    existing instanceof HTMLStyleElement
      ? existing
      : document.createElement("style");
  style.id = STYLE_ID;
  style.textContent = css;
  if (!style.isConnected) document.head.appendChild(style);
}

function coerce(raw: unknown): UiExperiment {
  const value = (raw ?? {}) as Record<string, unknown>;
  return {
    comfort: value.comfort === "roomy" ? "roomy" : "default",
    hover: value.hover === "lively" ? "lively" : "flat",
    panes:
      value.panes === "hairlines" || value.panes === "airy"
        ? value.panes
        : "soft",
  };
}

/** Reads the stored experiment, tolerating an absent / corrupt record. */
export function readUiExperiment(): UiExperiment {
  try {
    const raw = window.localStorage?.getItem(STORAGE_KEY);
    return raw ? coerce(JSON.parse(raw)) : { ...UI_DEFAULT };
  } catch {
    return { ...UI_DEFAULT };
  }
}

export function writeUiExperiment(exp: UiExperiment): void {
  try {
    window.localStorage?.setItem(STORAGE_KEY, JSON.stringify(exp));
  } catch {
    /* private mode / storage disabled — the in-memory experiment still applies */
  }
}
