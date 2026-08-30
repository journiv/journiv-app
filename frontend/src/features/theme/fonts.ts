import type { BundledFont } from "./types";

/**
 * Bundled font registry. DM Sans ships in the main CSS bundle; every other
 * family is loaded on demand (on selection, or on load when a stored theme
 * names it) so an unused face never costs the PWA anything. No remote fonts —
 * a self-hosted Journiv makes no external requests (DESIGN.md §13 privacy).
 */

type FontEntry = {
  label: string;
  /** Value for `--font-sans` / `--font-reader`. */
  stack: string;
  /** Idempotently ensures the face is available. */
  load: () => void;
};

const loaded = new Set<BundledFont>(["dm-sans"]);

function lazy(id: BundledFont, importer: () => Promise<unknown>) {
  return () => {
    if (loaded.has(id)) return;
    loaded.add(id);
    void importer().catch(() => loaded.delete(id));
  };
}

export const FONTS: Record<BundledFont, FontEntry> = {
  "dm-sans": {
    label: "DM Sans",
    stack: `"DM Sans Variable", ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif`,
    load: () => {},
  },
  lora: {
    label: "Lora",
    stack: `"Lora Variable", Georgia, "Iowan Old Style", "Times New Roman", serif`,
    load: lazy("lora", () => import("@fontsource-variable/lora/index.css")),
  },
};

export const FONT_OPTIONS: { value: BundledFont; label: string }[] = (
  Object.keys(FONTS) as BundledFont[]
).map((value) => ({ value, label: FONTS[value].label }));

export function fontStack(id: BundledFont | undefined): string | undefined {
  return id ? FONTS[id].stack : undefined;
}

export function ensureFont(id: BundledFont | undefined): void {
  if (id) FONTS[id].load();
}
