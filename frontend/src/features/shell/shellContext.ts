import { createContext, useContext } from "react";

export type ShellContextValue = {
  /** Opens the compact navigation drawer. */
  openNavigation: () => void;
  /** Opens the Quick Log capture sheet (docs/features/quicklog.md). */
  openQuickLog: () => void;
};

export const ShellContext = createContext<ShellContextValue>({
  openNavigation: () => {},
  openQuickLog: () => {},
});

/** Panes and the sidebar read this for shell-level affordances (the compact
 *  navigation trigger in a PageBar, the Quick Log entry points). */
export function useShell() {
  return useContext(ShellContext);
}
