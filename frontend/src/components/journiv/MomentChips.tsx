import type { MomentResponse } from "../../api/generated/types.gen";
import { cx } from "../../lib/cx";
import { PersonChip, TagChip } from "./PersonChip";

/**
 * People and tags for a Moment, rendered identically in the reader and the
 * editor so that reading and writing show the same metadata the same way.
 *
 * People and tags are deliberately NOT `MomentMeta` (docs/domain/moments.md): a person
 * has a face and a name, a tag is a word, and they never share a chip. This
 * component only displays them — editing lives in the editor's Details popover.
 *
 * Renders nothing when the Moment has neither, so callers can drop it in
 * unconditionally.
 */
export function MomentChips({
  moment,
  className,
  scopeLinks = false,
}: {
  moment: MomentResponse | undefined;
  className?: string;
  /** Render each chip as a link to the Timeline scoped to that person or tag
   *  (docs/features/library.md). The reader sets this; the editor never does — a chip you
   *  are editing is not a navigation target. */
  scopeLinks?: boolean;
}) {
  const people = moment?.people ?? [];
  const tags = moment?.tags ?? [];
  if (!people.length && !tags.length) return null;

  return (
    <div className={cx("jv-moment-chips", className)}>
      {people.length > 0 && (
        <section className="jv-moment-chips__row" aria-label="People">
          {people.map((person) => (
            <PersonChip
              key={person.id}
              person={person}
              to={scopeLinks ? { person: person.id } : undefined}
            />
          ))}
        </section>
      )}
      {tags.length > 0 && (
        <section className="jv-moment-chips__row" aria-label="Tags">
          {tags.map((tag) => (
            <TagChip
              key={tag.id}
              name={tag.name}
              to={scopeLinks ? { tag: tag.id } : undefined}
            />
          ))}
        </section>
      )}
    </div>
  );
}
