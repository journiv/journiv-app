import {
  Popover,
  PopoverContent,
  PopoverTitle,
  PopoverTrigger,
} from "../../components/ui/popover";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { LocateFixed, RotateCw, SlidersHorizontal, X } from "lucide-react";
import { useCallback, useMemo, useState } from "react";
import { api } from "../../api/client/api";
import type {
  LocationResult,
  MomentResponse,
  WeatherData,
} from "../../api/generated/types.gen";
import { queryKeys } from "../../api/query/keys";
import {
  moodsQuery,
  peopleQuery,
  tagSearchQuery,
} from "../../api/query/options";
import { ImmichSuggestedPeople } from "./immich/ImmichSuggestedPeople";
import { locationLabel, moodColor } from "../../components/journiv/MomentMeta";
import { Button } from "../../components/ui/button";
import { IconButton } from "../../components/ui/icon-button";
import { Skeleton } from "../../components/ui/skeleton";
import { StatusView } from "../../components/journiv/StatusView";
import {
  coordinateLabel,
  geolocationErrorMessage,
  getCurrentPosition,
} from "../../lib/geolocation";
import { Input } from "../../components/ui/input";

/**
 * Editing for the metadata the reader shows via `MomentMeta` and `MomentChips`:
 * mood, location, weather, people and tags. Lives in the editor toolbar's Insert
 * group as a single "Details" control (docs/features/editor.md) because five separate
 * toolbar buttons would crowd the bar.
 *
 * Every write needs a server `moment_id`. A brand-new entry has none until the
 * first real intent, so `ensureMomentId` creates the draft Moment on demand —
 * the same lazy-draft path media attachment uses. `onSaved(id)` refreshes the
 * editor's live Moment so the header and foot chips update immediately.
 */
export type MomentDetailsPanelProps = {
  /** Current values. Undefined until a draft Moment exists. */
  moment: MomentResponse | undefined;
  /** Resolves the Moment id, creating a draft if needed. Null when blocked. */
  ensureMomentId: () => Promise<string | null>;
  /** Called with the saved Moment id so the caller can refetch it. */
  onSaved: (momentId: string) => void;
  /** Timestamp/zone of the entry, for time-accurate weather lookup. */
  loggedAtUtc: string;
  loggedTimezone: string;
  disabled?: boolean;
  /** True when the moment holds Immich-origin media — gates the "Suggested
   *  from Immich" people strip so a non-Immich entry makes no face call. */
  hasImmichMedia?: boolean;
};

/** Free-text weather summary, matching the seed-data shape ("Clear 14°C"). */
export function formatWeatherSummary(weather: WeatherData): string {
  return `${weather.condition} ${Math.round(weather.temp_c)}°C`;
}

/** The `location_json` the backend stores — documented keys only, no coords derived. */
function locationJson(result: LocationResult): Record<string, unknown> {
  return {
    name: result.name,
    locality: result.locality ?? null,
    admin_area: result.admin_area ?? null,
    country: result.country ?? null,
    latitude: result.latitude,
    longitude: result.longitude,
    timezone: result.timezone ?? null,
  };
}

type RunWithMoment = (
  fn: (momentId: string) => Promise<unknown>,
) => Promise<void>;

/**
 * Fetches weather for a coordinate at the entry's own time and stores a summary.
 * Shared by the manual "Fetch" button and the "Use current location" flow.
 * Returns the service's message when weather lookup is switched off server-side.
 */
async function fetchAndStoreWeather(
  runWithMoment: RunWithMoment,
  coords: { latitude: number; longitude: number },
  loggedAtUtc: string,
  loggedTimezone: string,
): Promise<{ disabledMessage?: string }> {
  const response = await api.fetchWeather({
    latitude: coords.latitude,
    longitude: coords.longitude,
    entry_datetime_utc: loggedAtUtc,
    entry_timezone: loggedTimezone,
  });
  if (!("weather" in response)) return { disabledMessage: response.message };
  const summary = formatWeatherSummary(response.weather);
  await runWithMoment((id) =>
    api.updateMoment(id, {
      weather_summary: summary,
      weather_json: response.weather as unknown as Record<string, unknown>,
    }),
  );
  return {};
}

const NO_MOMENT = "no-moment";

function sectionError(
  isError: boolean,
  error: unknown,
  message: string,
): string | null {
  if (!isError) return null;
  // The page-level "Choose a Journal first" notice already covers this case.
  if (error instanceof Error && error.message === NO_MOMENT) return null;
  return message;
}

export function MomentDetailsPopover(props: MomentDetailsPanelProps) {
  return (
    <Popover>
      {/* No onPointerDown/preventDefault here: unlike the formatting buttons,
          the metadata popover does not depend on the editor selection. */}
      <PopoverTrigger
        render={<IconButton label="Moment details" />}
        disabled={props.disabled}
      >
        <SlidersHorizontal aria-hidden="true" size={16} />
      </PopoverTrigger>
      <PopoverContent align="end" sideOffset={8} className="jv-details-popover">
        <PopoverTitle className="jv-section-title">Moment details</PopoverTitle>
        <MomentDetailsPanel {...props} />
      </PopoverContent>
    </Popover>
  );
}

export function MomentDetailsPanel({
  moment,
  ensureMomentId,
  onSaved,
  loggedAtUtc,
  loggedTimezone,
  disabled = false,
  hasImmichMedia = false,
}: MomentDetailsPanelProps) {
  const runWithMoment = useCallback(
    async (fn: (momentId: string) => Promise<unknown>) => {
      const id = moment?.id ?? (await ensureMomentId());
      if (!id) throw new Error(NO_MOMENT);
      await fn(id);
      onSaved(id);
    },
    [moment?.id, ensureMomentId, onSaved],
  );

  return (
    <div className="jv-details">
      <MoodSection
        moment={moment}
        disabled={disabled}
        runWithMoment={runWithMoment}
      />
      <LocationSection
        moment={moment}
        disabled={disabled}
        loggedAtUtc={loggedAtUtc}
        loggedTimezone={loggedTimezone}
        runWithMoment={runWithMoment}
      />
      <WeatherSection
        moment={moment}
        disabled={disabled}
        loggedAtUtc={loggedAtUtc}
        loggedTimezone={loggedTimezone}
        runWithMoment={runWithMoment}
      />
      <PeopleSection
        moment={moment}
        disabled={disabled}
        runWithMoment={runWithMoment}
        hasImmichMedia={hasImmichMedia}
      />
      <TagsSection
        moment={moment}
        disabled={disabled}
        runWithMoment={runWithMoment}
      />
    </div>
  );
}

type SectionProps = {
  moment: MomentResponse | undefined;
  disabled: boolean;
  runWithMoment: (fn: (momentId: string) => Promise<unknown>) => Promise<void>;
};

/* ---- mood ------------------------------------------------------------- */

function MoodSection({ moment, disabled, runWithMoment }: SectionProps) {
  const moods = useQuery(moodsQuery());
  const mutation = useMutation({
    mutationFn: (moodId: string | null) =>
      runWithMoment((id) => api.updateMoment(id, { primary_mood_id: moodId })),
  });
  const current = moment?.primary_mood_id ?? null;
  const busy = disabled || mutation.isPending;
  const error = sectionError(
    mutation.isError,
    mutation.error,
    "Mood couldn't be saved. Try again.",
  );

  return (
    <section className="jv-details__section">
      <p className="jv-label">Mood</p>
      {moods.isLoading && <Skeleton height="1.75rem" />}
      {moods.isError && (
        <StatusView
          role="alert"
          tone="danger"
          title="Moods didn't load"
          action={
            <Button
              size="sm"
              variant="secondary"
              onClick={() => moods.refetch()}
            >
              Try again
            </Button>
          }
        />
      )}
      {moods.data?.length === 0 && (
        <StatusView
          title="No moods yet"
          description="Moods are managed in the mobile app's settings."
        />
      )}
      {moods.data && moods.data.length > 0 && (
        <div className="jv-details__options">
          <button
            type="button"
            className="jv-details__option"
            aria-pressed={current === null}
            disabled={busy}
            onClick={() => mutation.mutate(null)}
          >
            None
          </button>
          {moods.data.map((mood) => (
            <button
              key={mood.id}
              type="button"
              className="jv-details__option"
              aria-pressed={current === mood.id}
              disabled={busy}
              onClick={() => mutation.mutate(mood.id)}
            >
              <span
                className="jv-mood-dot"
                aria-hidden="true"
                style={
                  {
                    "--mood-accent": moodColor(mood.color_value),
                  } as React.CSSProperties
                }
              />
              {mood.name}
            </button>
          ))}
        </div>
      )}
      {error && (
        <p className="jv-details__error" role="alert">
          {error}
        </p>
      )}
    </section>
  );
}

/* ---- location ------------------------------------------------------------ */

/** Carries a ready-to-show message for a failed "Use current location" step. */
class DetectError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "DetectError";
  }
}

function LocationSection({
  moment,
  disabled,
  loggedAtUtc,
  loggedTimezone,
  runWithMoment,
}: SectionProps & { loggedAtUtc: string; loggedTimezone: string }) {
  const [query, setQuery] = useState("");
  const search = useMutation({
    mutationFn: (value: string) => api.searchLocation(value),
  });
  const clearSearch = () => {
    setQuery("");
    search.reset();
  };
  const save = useMutation({
    mutationFn: (result: LocationResult | null) =>
      runWithMoment((id) =>
        api.updateMoment(id, {
          location_json: result ? locationJson(result) : null,
          latitude: result?.latitude ?? null,
          longitude: result?.longitude ?? null,
        }),
      ),
    // The chosen place is now the current location; a stale result list
    // sitting under the field would just be noise.
    onSuccess: clearSearch,
  });
  // Device geolocation → reverse geocode → save location → fill weather too.
  // The manual controls stay available for overriding any of it.
  const detect = useMutation({
    mutationFn: async () => {
      let coords: { latitude: number; longitude: number };
      try {
        coords = await getCurrentPosition();
      } catch (error) {
        throw new DetectError(geolocationErrorMessage(error));
      }
      let place: LocationResult;
      try {
        place = await api.reverseGeocode(coords.latitude, coords.longitude);
      } catch {
        // Reverse geocoding is best-effort; the coordinates are still useful.
        place = { name: coordinateLabel(coords), ...coords };
      }
      await runWithMoment((id) =>
        api.updateMoment(id, {
          location_json: locationJson(place),
          latitude: place.latitude,
          longitude: place.longitude,
        }),
      );
      return fetchAndStoreWeather(
        runWithMoment,
        place,
        loggedAtUtc,
        loggedTimezone,
      );
    },
    onSuccess: clearSearch,
  });

  const current = moment ? locationLabel(moment) : null;
  const busy = disabled || save.isPending || detect.isPending;
  const results = search.data?.results ?? [];
  const saveError = sectionError(
    save.isError,
    save.error,
    "Location couldn't be saved. Try again.",
  );
  const detectError = !detect.isError
    ? null
    : detect.error instanceof DetectError
      ? detect.error.message
      : sectionError(
          true,
          detect.error,
          "Your location couldn't be saved. Try again.",
        );

  return (
    <section className="jv-details__section">
      <p className="jv-label">Location</p>
      {current && (
        <p className="jv-details__current">
          <span className="jv-truncate">{current}</span>
          <Button
            size="sm"
            variant="ghost"
            disabled={busy}
            onClick={() => save.mutate(null)}
          >
            Remove
          </Button>
        </p>
      )}
      <Button
        size="sm"
        variant="secondary"
        disabled={busy}
        onClick={() => detect.mutate()}
      >
        <LocateFixed aria-hidden="true" size={15} />
        {detect.isPending ? "Detecting…" : "Use current location"}
      </Button>
      {detectError && (
        <p className="jv-details__error" role="alert">
          {detectError}
        </p>
      )}
      {detect.data?.disabledMessage && (
        <p className="jv-caption">
          Location saved. {detect.data.disabledMessage}
        </p>
      )}
      <form
        className="jv-details__row"
        onSubmit={(event) => {
          event.preventDefault();
          if (query.trim()) search.mutate(query.trim());
        }}
      >
        <Input
          aria-label="Search for a place"
          placeholder="Search for a place"
          value={query}
          disabled={busy}
          onChange={(event) => setQuery(event.target.value)}
          autoCapitalize="none"
          autoCorrect="off"
        />
        <Button
          type="submit"
          size="sm"
          variant="secondary"
          disabled={busy || search.isPending || !query.trim()}
        >
          {search.isPending ? "Searching…" : "Search"}
        </Button>
      </form>
      {search.isError && (
        <p className="jv-details__error" role="alert">
          Couldn't search for that place. Try again.
        </p>
      )}
      {search.isSuccess && results.length === 0 && (
        <p className="jv-caption">No places matched "{query.trim()}".</p>
      )}
      {results.length > 0 && (
        <div className="jv-details__results">
          {results.map((result) => (
            <button
              key={`${result.name}:${result.latitude},${result.longitude}`}
              type="button"
              className="jv-details__result"
              disabled={busy}
              onClick={() => save.mutate(result)}
            >
              {result.name}
            </button>
          ))}
        </div>
      )}
      {saveError && (
        <p className="jv-details__error" role="alert">
          {saveError}
        </p>
      )}
    </section>
  );
}

/* ---- weather ----------------------------------------------------------- */

function WeatherSection({
  moment,
  disabled,
  loggedAtUtc,
  loggedTimezone,
  runWithMoment,
}: SectionProps & { loggedAtUtc: string; loggedTimezone: string }) {
  const [manual, setManual] = useState("");
  const [disabledMessage, setDisabledMessage] = useState<string | null>(null);
  const hasCoords =
    typeof moment?.latitude === "number" &&
    typeof moment?.longitude === "number";

  const fetchWeather = useMutation({
    mutationFn: async () => {
      setDisabledMessage(null);
      const { disabledMessage: off } = await fetchAndStoreWeather(
        runWithMoment,
        {
          latitude: moment?.latitude as number,
          longitude: moment?.longitude as number,
        },
        loggedAtUtc,
        loggedTimezone,
      );
      if (off) setDisabledMessage(off);
    },
  });
  const saveManual = useMutation({
    mutationFn: (value: string) =>
      runWithMoment((id) =>
        api.updateMoment(id, { weather_summary: value || null }),
      ),
    onSuccess: () => setManual(""),
  });

  const current = moment?.weather_summary?.trim() || null;
  const busy = disabled || fetchWeather.isPending || saveManual.isPending;
  const fetchError = sectionError(
    fetchWeather.isError,
    fetchWeather.error,
    "Weather couldn't be fetched. Try again.",
  );
  const manualError = sectionError(
    saveManual.isError,
    saveManual.error,
    "Weather couldn't be saved. Try again.",
  );

  return (
    <section className="jv-details__section">
      <p className="jv-label">Weather</p>
      {current && (
        <p className="jv-details__current">
          <span className="jv-truncate">{current}</span>
          <Button
            size="sm"
            variant="ghost"
            disabled={busy}
            onClick={() => saveManual.mutate("")}
          >
            Remove
          </Button>
        </p>
      )}
      {hasCoords ? (
        <Button
          size="sm"
          variant="secondary"
          disabled={busy}
          onClick={() => fetchWeather.mutate()}
        >
          {fetchWeather.isPending ? "Fetching…" : "Fetch for this location"}
        </Button>
      ) : (
        <p className="jv-caption">
          Add a location to fetch weather automatically.
        </p>
      )}
      <form
        className="jv-details__row"
        onSubmit={(event) => {
          event.preventDefault();
          if (manual.trim()) {
            saveManual.mutate(manual.trim());
          }
        }}
      >
        <Input
          aria-label="Weather summary"
          placeholder="Or type it, e.g. Clear 14°C"
          value={manual}
          disabled={busy}
          onChange={(event) => setManual(event.target.value)}
        />
        <Button
          type="submit"
          size="sm"
          variant="secondary"
          disabled={busy || !manual.trim()}
        >
          Save
        </Button>
      </form>
      {disabledMessage && <p className="jv-caption">{disabledMessage}</p>}
      {fetchError && (
        <p className="jv-details__error" role="alert">
          {fetchError}
        </p>
      )}
      {manualError && (
        <p className="jv-details__error" role="alert">
          {manualError}
        </p>
      )}
    </section>
  );
}

/* ---- people ---------------------------------------------------------- */

function PeopleSection({
  moment,
  disabled,
  runWithMoment,
  hasImmichMedia = false,
}: SectionProps & { hasImmichMedia?: boolean }) {
  const [filter, setFilter] = useState("");
  const queryClient = useQueryClient();
  const people = useQuery(peopleQuery());
  const mutation = useMutation({
    mutationFn: (personIds: string[]) =>
      runWithMoment((id) => api.setMomentPeople(id, personIds)),
    onSuccess: () => {
      // A person the writer just added is no longer a "suggestion" — let the
      // server recompute the strip.
      if (moment?.id) {
        queryClient.invalidateQueries({
          queryKey: queryKeys.immichPeopleSuggestions(moment.id),
        });
      }
    },
  });
  const selected = useMemo(
    () => new Set((moment?.people ?? []).map((person) => person.id)),
    [moment?.people],
  );
  const busy = disabled || mutation.isPending;
  const error = sectionError(
    mutation.isError,
    mutation.error,
    "People couldn't be saved. Try again.",
  );

  const active = (people.data ?? []).filter((person) => !person.archived_at);
  const term = filter.trim().toLowerCase();
  const shown = term
    ? active.filter((person) =>
        `${person.name} ${person.nickname ?? ""}`.toLowerCase().includes(term),
      )
    : active;

  const toggle = (personId: string, checked: boolean) => {
    const next = checked
      ? [...selected, personId]
      : [...selected].filter((id) => id !== personId);
    mutation.mutate(next);
  };

  return (
    <section className="jv-details__section">
      <p className="jv-label">People</p>
      <ImmichSuggestedPeople
        momentId={moment?.id}
        enabled={hasImmichMedia && Boolean(moment?.id)}
        selectedIds={selected}
        busy={busy}
        onAdd={(personId) => mutation.mutate([...selected, personId])}
        onAddAll={(personIds) =>
          mutation.mutate([...new Set([...selected, ...personIds])])
        }
      />
      {people.isLoading && <Skeleton height="1.75rem" />}
      {people.isError && (
        <StatusView
          role="alert"
          tone="danger"
          title="People didn't load"
          action={
            <Button
              size="sm"
              variant="secondary"
              onClick={() => people.refetch()}
            >
              Try again
            </Button>
          }
        />
      )}
      {people.data?.length === 0 && (
        <StatusView
          title="No people yet"
          description="Add people in the mobile app to tag them here."
        />
      )}
      {active.length > 0 && (
        <>
          <Input
            aria-label="Filter people"
            placeholder="Filter people"
            value={filter}
            disabled={busy}
            onChange={(event) => setFilter(event.target.value)}
          />
          <div className="jv-details__people">
            {shown.map((person) => (
              <label key={person.id} className="jv-details__person">
                <input
                  type="checkbox"
                  checked={selected.has(person.id)}
                  disabled={busy}
                  onChange={(event) => toggle(person.id, event.target.checked)}
                />
                <span className="jv-truncate">{person.name}</span>
              </label>
            ))}
            {shown.length === 0 && (
              <p className="jv-caption">No people matched "{filter.trim()}".</p>
            )}
          </div>
        </>
      )}
      {error && (
        <p className="jv-details__error" role="alert">
          {error}
        </p>
      )}
    </section>
  );
}

/* ---- tags ---------------------------------------------------------------- */

function TagsSection({ moment, disabled, runWithMoment }: SectionProps) {
  const [value, setValue] = useState("");
  const add = useMutation({
    mutationFn: (names: string[]) =>
      runWithMoment((id) => api.addMomentTags(id, names)),
    onSuccess: () => setValue(""),
  });
  const remove = useMutation({
    mutationFn: (tagId: string) =>
      runWithMoment((id) => api.removeMomentTag(id, tagId)),
  });
  const current = moment?.tags ?? [];
  const currentNames = new Set(current.map((tag) => tag.name.toLowerCase()));
  const busy = disabled || add.isPending || remove.isPending;

  const term = value.trim();
  const suggestions = useQuery({
    ...tagSearchQuery(term),
    enabled: term.length >= 1,
  });
  const suggested = (suggestions.data ?? [])
    .filter((tag) => !currentNames.has(tag.name.toLowerCase()))
    .slice(0, 6);

  const commit = (raw: string) => {
    const names = raw
      .split(",")
      .map((name) => name.trim())
      .filter((name) => name && !currentNames.has(name.toLowerCase()));
    if (names.length) add.mutate([...new Set(names)]);
  };

  const addError = sectionError(
    add.isError,
    add.error,
    "Tag couldn't be added. Try again.",
  );
  const removeError = sectionError(
    remove.isError,
    remove.error,
    "Tag couldn't be removed. Try again.",
  );

  return (
    <section className="jv-details__section">
      <p className="jv-label">Tags</p>
      {current.length > 0 && (
        <div className="jv-details__tags">
          {current.map((tag) => (
            <span key={tag.id} className="jv-details__tag">
              <span aria-hidden="true">#</span>
              {tag.name}
              <IconButton
                label={`Remove ${tag.name}`}
                size="sm"
                disabled={busy}
                onClick={() => remove.mutate(tag.id)}
              >
                <X aria-hidden="true" size={13} />
              </IconButton>
            </span>
          ))}
        </div>
      )}
      <form
        className="jv-details__row"
        onSubmit={(event) => {
          event.preventDefault();
          commit(value);
        }}
      >
        <Input
          aria-label="Add a tag"
          placeholder="Add a tag"
          value={value}
          disabled={busy}
          autoCapitalize="none"
          autoCorrect="off"
          onChange={(event) => setValue(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === ",") {
              event.preventDefault();
              commit(value);
            }
          }}
        />
        <Button
          type="submit"
          size="sm"
          variant="secondary"
          disabled={busy || !term}
        >
          {add.isPending ? "Adding…" : "Add"}
        </Button>
      </form>
      {suggested.length > 0 && (
        <div className="jv-details__results">
          {suggested.map((tag) => (
            <button
              key={tag.id}
              type="button"
              className="jv-details__result"
              disabled={busy}
              onClick={() => commit(tag.name)}
            >
              #{tag.name}
            </button>
          ))}
        </div>
      )}
      {suggestions.isError && (
        <p className="jv-caption">
          <RotateCw aria-hidden="true" size={12} /> Suggestions unavailable.
        </p>
      )}
      {addError && (
        <p className="jv-details__error" role="alert">
          {addError}
        </p>
      )}
      {removeError && (
        <p className="jv-details__error" role="alert">
          {removeError}
        </p>
      )}
    </section>
  );
}
