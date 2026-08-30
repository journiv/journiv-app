import { Link } from "@tanstack/react-router";
import { NotebookText } from "lucide-react";
import { DropdownMenuItem } from "../../components/ui/dropdown-menu";

/** One entity scope for the Timeline: exactly one key, the entity's id. */
export type MomentScopeParam =
  | { person: string }
  | { tag: string }
  | { activity: string }
  | { mood: string }
  | { goal: string };

/**
 * "View moments" — the standard leading item in a Library entity's ⋯ menu
 * (People, Activities, Goals, Moods). It opens the Timeline scoped to that
 * entity (DESIGN.md §24), so every entity reaches its moments the same way.
 */
export function ViewMomentsMenuItem({ scope }: { scope: MomentScopeParam }) {
  return (
    <DropdownMenuItem
      render={<Link to="/timeline" search={{ q: "", ...scope }} />}
    >
      <NotebookText aria-hidden="true" size={15} />
      View moments
    </DropdownMenuItem>
  );
}
