import { Link } from "@tanstack/react-router";
import type { PersonSummaryResponse } from "../../api/generated/types.gen";
import { Avatar, AvatarFallback, AvatarImage } from "../ui/avatar";
import { Badge } from "../ui/badge";

/** People and tags are deliberately different objects. A person has a face and
 *  a name; a tag is a word. Never render them with the same chip.
 *
 *  When `to` is given the chip is a link to the Timeline scoped to that entity
 *  (docs/features/library.md) — used at the reader foot, never in the editor. */
export function PersonChip({
  person,
  to,
}: {
  person: PersonSummaryResponse;
  to?: { person: string };
}) {
  const initial = (person.name || "?").trim().charAt(0).toUpperCase();
  const inner = (
    <>
      <Avatar className="jv-person__avatar" aria-hidden="true">
        {person.profile_image_url && (
          <AvatarImage src={person.profile_image_url} alt="" loading="lazy" />
        )}
        <AvatarFallback>{initial}</AvatarFallback>
      </Avatar>
      <span className="jv-truncate">{person.name}</span>
    </>
  );
  return to ? (
    <Badge
      variant="outline"
      className="jv-person jv-person--link"
      render={<Link to="/timeline" search={{ q: "", ...to }} />}
    >
      {inner}
    </Badge>
  ) : (
    <Badge variant="outline" className="jv-person">
      {inner}
    </Badge>
  );
}

export function TagChip({ name, to }: { name: string; to?: { tag: string } }) {
  const inner = (
    <>
      <span aria-hidden="true">#</span>
      {name}
    </>
  );
  return to ? (
    <Badge
      variant="secondary"
      render={<Link to="/timeline" search={{ q: "", ...to }} />}
    >
      {inner}
    </Badge>
  ) : (
    <Badge variant="secondary">{inner}</Badge>
  );
}
