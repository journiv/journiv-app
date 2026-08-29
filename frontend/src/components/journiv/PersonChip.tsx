import { Link } from "@tanstack/react-router";
import type { PersonSummaryResponse } from "../../api/generated/types.gen";

/** People and tags are deliberately different objects. A person has a face and
 *  a name; a tag is a word. Never render them with the same chip.
 *
 *  When `to` is given the chip is a link to the Timeline scoped to that entity
 *  (DESIGN.md §24) — used at the reader foot, never in the editor. */
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
      {person.profile_image_url ? (
        <img
          className="jv-person__avatar"
          src={person.profile_image_url}
          alt=""
          loading="lazy"
        />
      ) : (
        <span
          className="jv-person__avatar jv-person__avatar--initial"
          aria-hidden="true"
        >
          {initial}
        </span>
      )}
      <span className="jv-truncate">{person.name}</span>
    </>
  );
  return to ? (
    <Link
      className="jv-person jv-person--link"
      to="/timeline"
      search={{ q: "", ...to }}
    >
      {inner}
    </Link>
  ) : (
    <span className="jv-person">{inner}</span>
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
    <Link
      className="jv-tag jv-tag--link"
      to="/timeline"
      search={{ q: "", ...to }}
    >
      {inner}
    </Link>
  ) : (
    <span className="jv-tag">{inner}</span>
  );
}
