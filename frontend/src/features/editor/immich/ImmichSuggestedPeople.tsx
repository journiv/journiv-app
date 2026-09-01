import { Plus } from "lucide-react";
import { Button } from "../../../components/ui/button";
import { useImmichPeopleSuggestions } from "./useImmichPeopleSuggestions";

/**
 * "Suggested from Immich" — a quiet strip at the top of the editor's People
 * section. When the moment holds Immich media, Immich's face index is asked
 * which sync-enabled people appear in it; each match is an add-chip. It never
 * writes on its own (DESIGN §2.6) — a tap runs the section's own
 * `setMomentPeople`. A fetch failure is not a failed user action, so it shows a
 * quiet caption with a retry, never a `role="alert"` (the reader-media
 * precedent, §13).
 */
export function ImmichSuggestedPeople({
  momentId,
  enabled,
  selectedIds,
  busy,
  onAdd,
  onAddAll,
}: {
  momentId: string | undefined;
  enabled: boolean;
  selectedIds: Set<string>;
  busy: boolean;
  onAdd: (personId: string) => void;
  onAddAll: (personIds: string[]) => void;
}) {
  const suggestions = useImmichPeopleSuggestions(momentId, enabled);

  if (!enabled) return null;

  if (suggestions.isError) {
    return (
      <p className="jv-details__suggest-note jv-caption" role="status">
        Couldn’t check Immich for people.{" "}
        <Button variant="link" size="sm" onClick={() => suggestions.refetch()}>
          Retry
        </Button>
      </p>
    );
  }

  const people = (suggestions.data?.people ?? []).filter(
    (person) => !selectedIds.has(person.id),
  );
  if (suggestions.isLoading || people.length === 0) return null;

  return (
    <div className="jv-details__suggest">
      <p className="jv-caption">Suggested from Immich</p>
      <div className="jv-details__suggest-chips">
        {people.map((person) => (
          <button
            key={person.id}
            type="button"
            className="jv-details__suggest-chip"
            disabled={busy}
            onClick={() => onAdd(person.id)}
          >
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
                {(person.name || "?").trim().charAt(0).toUpperCase()}
              </span>
            )}
            <span className="jv-truncate">{person.name}</span>
            <Plus aria-hidden="true" size={13} />
          </button>
        ))}
        {people.length > 1 && (
          <Button
            variant="link"
            size="sm"
            disabled={busy}
            onClick={() => onAddAll(people.map((person) => person.id))}
          >
            Add all
          </Button>
        )}
      </div>
    </div>
  );
}
