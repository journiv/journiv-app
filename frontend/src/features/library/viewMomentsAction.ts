import { NotebookText } from "lucide-react";
import type { AppMenuAction } from "../../components/journiv/AppAdaptiveMenu";

/** One entity scope for the Timeline: exactly one key, the entity's id. */
export type MomentScopeParam =
  | { person: string }
  | { tag: string }
  | { activity: string }
  | { mood: string }
  | { goal: string };

/**
 * "View moments" — the standard leading action in a Library entity's ⋯ menu
 * (People, Tags, Activities, Goals, Moods). It opens the Timeline scoped to
 * that entity (docs/features/library.md), so every entity reaches its moments the same
 * way.
 *
 * This is an action *descriptor*, not a rendered menu item: `AppAdaptiveMenu`
 * presents it as a `DropdownMenuItem` above 860px and as an action-sheet row
 * below, and a pre-rendered `DropdownMenuItem` could not be either.
 */
export function viewMomentsAction(scope: MomentScopeParam): AppMenuAction {
  return {
    kind: "link",
    id: "view-moments",
    label: "View moments",
    icon: NotebookText,
    link: { to: "/timeline", search: { q: "", ...scope } },
  };
}
