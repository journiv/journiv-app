import type {
  ActivityResponse,
  MomentResponse,
} from "../../api/generated/types.gen";
import { cx } from "../../lib/cx";
import { ActivityChip, PersonChip, TagChip } from "./PersonChip";

/**
 * People, activities and tags for a Moment, rendered identically in the
 * reader and the editor so that reading and writing show the same metadata
 * the same way.
 *
 * People, activities and tags are deliberately NOT `MomentMeta`
 * (docs/domain/moments.md): a person has a face and a name, an activity has a
 * Library-assigned icon and colour, a tag is a word, and they never share a
 * chip. This component only displays them — editing lives in the editor's
 * Details popover.
 *
 * Renders nothing when the Moment has none of the three, so callers can drop
 * it in unconditionally.
 */
export function MomentChips({
  moment,
  className,
  scopeLinks = false,
}: {
  moment: MomentResponse | undefined;
  className?: string;
  /** Render each chip as a link to the Timeline scoped to that person, activity,
   *  or tag (docs/features/library.md). The reader sets this; the editor never
   *  does — a chip you are editing is not a navigation target. */
  scopeLinks?: boolean;
}) {
  const people = moment?.people ?? [];
  const tags = moment?.tags ?? [];
  // `mood_activity` can hold more than one link per activity (a Daylio-import
  // mood pairing sits alongside the plain activity-only row this app writes),
  // so the chip list is deduplicated by activity id.
  const activities = Array.from(
    new Map(
      (moment?.mood_activity ?? [])
        .map((link) => link.activity)
        .filter((activity): activity is ActivityResponse => Boolean(activity))
        .map((activity) => [activity.id, activity] as const),
    ).values(),
  );
  if (!people.length && !activities.length && !tags.length) return null;

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
      {activities.length > 0 && (
        <section className="jv-moment-chips__row" aria-label="Activities">
          {activities.map((activity) => (
            <ActivityChip
              key={activity.id}
              activity={activity}
              to={scopeLinks ? { activity: activity.id } : undefined}
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
