/**
 * Manifest `shortcuts` (Android long-press icon menu; iOS ignores them).
 * Shared with vite.config.ts so the list has one source of truth and
 * manifestShortcuts.test.ts can assert every `url` resolves in the router.
 *
 * Never add a Quick Log shortcut here — it ships behind
 * QUICK_LOG_ENABLED = false (src/features/shell/shellContext.ts).
 */
export const manifestShortcuts = [
  { name: "New entry", short_name: "New", url: "/timeline/new" },
  { name: "Timeline", short_name: "Timeline", url: "/timeline" },
  { name: "Insights", short_name: "Insights", url: "/insights" },
] as const;
