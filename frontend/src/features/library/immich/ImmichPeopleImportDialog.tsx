import {
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { Check, X } from "lucide-react";
import { useEffect, useId, useMemo, useState } from "react";
import { api } from "../../../api/client/api";
import { ApiError } from "../../../api/client/errors";
import type {
  ImmichPeopleImportItem,
  PersonResponse,
} from "../../../api/generated/types.gen";
import { queryKeys } from "../../../api/query/keys";
import {
  immichPeopleInfiniteQuery,
  peopleQuery,
} from "../../../api/query/options";
import { StatusView } from "../../../components/journiv/StatusView";
import { AppAdaptiveDialog } from "../../../components/journiv/AppAdaptiveDialog";
import { Button } from "../../../components/ui/button";
import {
  Combobox,
  ComboboxContent,
  ComboboxEmpty,
  ComboboxInput,
  ComboboxItem,
  ComboboxList,
} from "../../../components/ui/combobox";
import { Input } from "../../../components/ui/input";
import { SearchInput } from "../../../components/ui/search-input";
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../../../components/ui/select";
import { Skeleton } from "../../../components/ui/skeleton";
import { Spinner } from "../../../components/ui/spinner";
import {
  buildImportItems,
  defaultRowState,
  type ImportOutcome,
  isRowIncomplete,
  partitionResults,
  type PersonRowState,
  type RowMode,
} from "./immichPeopleImport";
import "./immichPeopleImport.css";

const MODE_ITEMS: { value: RowMode; label: string }[] = [
  { value: "create", label: "Create new" },
  { value: "link", label: "Link to existing…" },
  { value: "skip", label: "Skip" },
];

const SKELETON_ROWS = 6;

function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  const glyph =
    parts.length > 1
      ? `${parts[0][0]}${parts.at(-1)?.[0]}`
      : (parts[0]?.[0] ?? "?");
  return glyph.toUpperCase();
}

function useDebounced<T>(value: T, delayMs: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(value), delayMs);
    return () => window.clearTimeout(timer);
  }, [value, delayMs]);
  return debounced;
}

function listError(error: unknown): { title: string; description: string } {
  if (error instanceof ApiError && error.status === 400) {
    return {
      title: "Immich needs reconnecting",
      description:
        "Reconnect Immich in Settings → Integrations, then try importing people again.",
    };
  }
  return {
    title: "Couldn’t reach Immich",
    description: "The people list didn’t load. Try again in a moment.",
  };
}

function importErrorDescription(error: unknown): string {
  return error instanceof Error && error.message
    ? error.message
    : "The import request failed. Try again in a moment.";
}

type View =
  | { kind: "browse" }
  | { kind: "importing"; count: number }
  | {
      kind: "results";
      outcome: ImportOutcome;
      nameByExternalId: Record<string, string>;
    };

/**
 * Library → People · "Import from Immich". One adaptive overlay, three in-place
 * views (browse → importing → results — they swap, never stack, DESIGN §24).
 * State lives in this caller above `AppAdaptiveDialog`, so crossing 860px does
 * not discard browse edits. The
 * browse list is a plain infinite-scroll list rather than the virtualized
 * `AssetGridPicker`, because each row carries its own mapping state (create /
 * link / skip) and a name field; named-people counts are modest and the server
 * `search` narrows further.
 */
export function ImmichPeopleImportDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const queryClient = useQueryClient();
  const syncId = useId();
  const [search, setSearch] = useState("");
  const debouncedSearch = useDebounced(search, 300);
  const [rowState, setRowState] = useState<Record<string, PersonRowState>>({});
  const [syncEnabled, setSyncEnabled] = useState(true);
  const [view, setView] = useState<View>({ kind: "browse" });

  const peopleList = useInfiniteQuery({
    ...immichPeopleInfiniteQuery(debouncedSearch),
    enabled: open,
  });
  const journivPeople = useQuery({ ...peopleQuery(), enabled: open });

  const immichPeople = useMemo(
    () => peopleList.data?.pages.flatMap((page) => page.people) ?? [],
    [peopleList.data],
  );

  // Seed row state for people we have not seen yet — never clobber an edit.
  useEffect(() => {
    if (immichPeople.length === 0) return;
    setRowState((current) => {
      let changed = false;
      const next = { ...current };
      for (const person of immichPeople) {
        if (!(person.external_person_id in next)) {
          next[person.external_person_id] = defaultRowState(person);
          changed = true;
        }
      }
      return changed ? next : current;
    });
  }, [immichPeople]);

  const activePeople = useMemo(
    () => (journivPeople.data ?? []).filter((person) => !person.archived_at),
    [journivPeople.data],
  );

  const entries = immichPeople.map((person) => ({
    person,
    row: rowState[person.external_person_id] ?? defaultRowState(person),
  }));
  const readyItems = buildImportItems(entries, syncEnabled);
  const incompleteCount = entries.filter(({ person, row }) =>
    isRowIncomplete(person, row),
  ).length;

  const importMutation = useMutation({
    mutationFn: (payload: ImmichPeopleImportItem[]) =>
      api.importImmichPeople({ people: payload }),
    onMutate: (payload) =>
      setView({ kind: "importing", count: payload.length }),
    onSuccess: (response) => {
      const outcome = partitionResults(response.results);
      const nameByExternalId: Record<string, string> = {};
      for (const { person, row } of entries) {
        nameByExternalId[person.external_person_id] =
          row.name.trim() || person.name?.trim() || "Immich person";
      }
      if (outcome.succeeded.length > 0) {
        queryClient.invalidateQueries({ queryKey: queryKeys.people });
      }
      setView({ kind: "results", outcome, nameByExternalId });
    },
    onError: () => setView({ kind: "browse" }),
  });

  const patchRow = (externalId: string, patch: Partial<PersonRowState>) =>
    setRowState((current) => ({
      ...current,
      [externalId]: {
        ...(current[externalId] ?? {
          mode: "skip",
          name: "",
          linkPersonId: null,
        }),
        ...patch,
      },
    }));

  const startImport = (externalIds?: string[]) => {
    const scoped = externalIds
      ? entries.filter(({ person }) =>
          externalIds.includes(person.external_person_id),
        )
      : entries;
    importMutation.mutate(buildImportItems(scoped, syncEnabled));
  };

  const close = () => {
    setSearch("");
    setRowState({});
    setSyncEnabled(true);
    setView({ kind: "browse" });
    onOpenChange(false);
  };

  const handleOpenChange = (nextOpen: boolean) => {
    if (!nextOpen) close();
    else onOpenChange(true);
  };

  if (view.kind === "importing") {
    return (
      <AppAdaptiveDialog
        open={open}
        onOpenChange={handleOpenChange}
        title="Import people from Immich"
        size="lg"
        dismissible={false}
      >
        <StatusView
          role="status"
          icon={<Spinner />}
          title={`Importing ${view.count} ${view.count === 1 ? "person" : "people"}…`}
        />
      </AppAdaptiveDialog>
    );
  }

  if (view.kind === "results") {
    const { succeeded, failed } = view.outcome;
    const description = `${
      succeeded.length > 0
        ? `${succeeded.length} ${succeeded.length === 1 ? "person" : "people"} imported.`
        : "No people were imported."
    }${failed.length > 0 ? ` ${failed.length} failed.` : ""}`;
    return (
      <AppAdaptiveDialog
        open={open}
        onOpenChange={handleOpenChange}
        title="Import finished"
        description={description}
        size="lg"
        footer={
          <>
            {failed.length > 0 && (
              <Button
                variant="secondary"
                disabled={importMutation.isPending}
                onClick={() =>
                  startImport(failed.map((result) => result.external_person_id))
                }
              >
                Retry failed
              </Button>
            )}
            <Button variant="default" onClick={close}>
              Done
            </Button>
          </>
        }
      >
        <div className="jv-immich-people-import__results">
          {succeeded.map((result) => (
            <p
              key={result.external_person_id}
              className="jv-immich-people-import__result jv-immich-people-import__result--ok jv-body"
            >
              <Check aria-hidden="true" size={15} />
              {result.mode === "link" ? "Linked " : "Created "}
              {result.person?.name ??
                view.nameByExternalId[result.external_person_id]}
            </p>
          ))}
          {failed.map((result) => (
            <p
              key={result.external_person_id}
              className="jv-immich-people-import__result jv-immich-people-import__result--fail jv-body"
              role="alert"
            >
              <X aria-hidden="true" size={15} />
              {view.nameByExternalId[result.external_person_id]}:{" "}
              {result.error ?? "Import failed."}
            </p>
          ))}
        </div>
      </AppAdaptiveDialog>
    );
  }

  return (
    <AppAdaptiveDialog
      open={open}
      onOpenChange={handleOpenChange}
      title="Import people from Immich"
      description="Create Journiv people from the faces Immich has identified, or link them to people you already have."
      size="lg"
      footer={
        <>
          <span
            className="jv-immich-people-import__count jv-caption"
            aria-live="polite"
          >
            {incompleteCount > 0
              ? `Finish ${incompleteCount} ${incompleteCount === 1 ? "row" : "rows"} to import`
              : `${readyItems.length} ready to import`}
          </span>
          <Button variant="ghost" onClick={close}>
            Cancel
          </Button>
          <Button
            variant="default"
            disabled={readyItems.length === 0 || incompleteCount > 0}
            onClick={() => startImport()}
          >
            {readyItems.length > 0
              ? `Import ${readyItems.length} ${readyItems.length === 1 ? "person" : "people"}`
              : "Import"}
          </Button>
        </>
      }
    >
      <div className="jv-immich-people-import">
        <SearchInput
          className="jv-immich-people-import__search"
          label="Search Immich people"
          placeholder="Search Immich people…"
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          onClear={() => setSearch("")}
        />

        {importMutation.isError && (
          <StatusView
            tone="danger"
            role="alert"
            title="Couldn’t import people"
            description={importErrorDescription(importMutation.error)}
          />
        )}

        <div className="jv-immich-people-import__scroll">
          {peopleList.isError ? (
            <StatusView
              tone="danger"
              role="alert"
              title={listError(peopleList.error).title}
              description={listError(peopleList.error).description}
              action={
                <Button
                  variant="secondary"
                  onClick={() => peopleList.refetch()}
                >
                  Try again
                </Button>
              }
            />
          ) : peopleList.isLoading ? (
            <ul className="jv-immich-people-import__list">
              {Array.from({ length: SKELETON_ROWS }, (_, index) => (
                // biome-ignore lint/suspicious/noArrayIndexKey: fixed count of identical placeholders that never reorder.
                <li key={index} className="jv-immich-people-import__row">
                  <Skeleton className="size-9 rounded-full" />
                  <Skeleton className="h-4 flex-1" />
                </li>
              ))}
            </ul>
          ) : immichPeople.length === 0 ? (
            <StatusView
              title={
                debouncedSearch.trim()
                  ? `No Immich people match “${debouncedSearch.trim()}”`
                  : "No people in Immich yet"
              }
              description={
                debouncedSearch.trim()
                  ? undefined
                  : "Immich groups faces into people as it scans your library."
              }
            />
          ) : (
            <ul className="jv-immich-people-import__list">
              {entries.map(({ person, row }) => (
                <li
                  key={person.external_person_id}
                  className="jv-immich-people-import__row"
                >
                  {person.thumbnail_url ? (
                    <img
                      className="jv-immich-people-import__avatar"
                      src={person.thumbnail_url}
                      alt=""
                      loading="lazy"
                      decoding="async"
                    />
                  ) : (
                    <span
                      className="jv-immich-people-import__avatar jv-immich-people-import__avatar--initial"
                      aria-hidden="true"
                    >
                      {initials(person.name ?? "?")}
                    </span>
                  )}

                  <div className="jv-immich-people-import__name">
                    {person.name ? (
                      <span className="jv-body jv-truncate">{person.name}</span>
                    ) : row.mode === "skip" ? (
                      <span className="jv-caption">Unnamed person</span>
                    ) : (
                      <Input
                        aria-label="Name this person"
                        placeholder="Name this person"
                        value={row.name}
                        aria-invalid={row.name.trim().length === 0}
                        onChange={(event) =>
                          patchRow(person.external_person_id, {
                            name: event.target.value,
                          })
                        }
                      />
                    )}
                    {row.mode === "link" && !row.linkPersonId && (
                      <span className="jv-caption">
                        Choose a person to link.
                      </span>
                    )}
                  </div>

                  {person.mapped_person ? (
                    <span className="jv-immich-people-import__linked jv-caption">
                      Linked to {person.mapped_person.name}
                    </span>
                  ) : (
                    <div className="jv-immich-people-import__controls">
                      <Select
                        items={MODE_ITEMS}
                        value={row.mode}
                        onValueChange={(value) =>
                          patchRow(person.external_person_id, {
                            mode: value as RowMode,
                          })
                        }
                      >
                        <SelectTrigger
                          aria-label={`Action for ${person.name ?? "this person"}`}
                        >
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent
                          alignItemWithTrigger={false}
                          align="start"
                        >
                          <SelectGroup>
                            {MODE_ITEMS.map((item) => (
                              <SelectItem key={item.value} value={item.value}>
                                {item.label}
                              </SelectItem>
                            ))}
                          </SelectGroup>
                        </SelectContent>
                      </Select>

                      {row.mode === "link" && (
                        <LinkPersonPicker
                          people={activePeople}
                          loading={journivPeople.isLoading}
                          value={row.linkPersonId}
                          onChange={(personId) =>
                            patchRow(person.external_person_id, {
                              linkPersonId: personId,
                            })
                          }
                        />
                      )}
                    </div>
                  )}
                </li>
              ))}
              {peopleList.hasNextPage && (
                <li className="jv-immich-people-import__row">
                  <Button
                    variant="ghost"
                    size="sm"
                    disabled={peopleList.isFetchingNextPage}
                    onClick={() => peopleList.fetchNextPage()}
                  >
                    {peopleList.isFetchingNextPage ? "Loading…" : "Load more"}
                  </Button>
                </li>
              )}
            </ul>
          )}
        </div>

        <label
          className="jv-immich-people-import__sync jv-caption"
          htmlFor={syncId}
        >
          <input
            id={syncId}
            type="checkbox"
            checked={syncEnabled}
            onChange={(event) => setSyncEnabled(event.target.checked)}
          />
          Suggest these people when their photos are added to an entry
        </label>
      </div>
    </AppAdaptiveDialog>
  );
}

function LinkPersonPicker({
  people,
  loading,
  value,
  onChange,
}: {
  people: PersonResponse[];
  loading: boolean;
  value: string | null;
  onChange: (personId: string | null) => void;
}) {
  const selected = people.find((person) => person.id === value) ?? null;
  return (
    <Combobox
      items={people}
      value={selected}
      onValueChange={(next) =>
        onChange(next && typeof next === "object" ? next.id : null)
      }
      itemToStringLabel={(person: PersonResponse) => person.name}
      itemToStringValue={(person: PersonResponse) => person.name}
      isItemEqualToValue={(a: PersonResponse, b: PersonResponse) =>
        a.id === b.id
      }
      disabled={loading}
    >
      <ComboboxInput
        aria-label="Link to Journiv person"
        placeholder={loading ? "Loading people…" : "Search people…"}
      />
      <ComboboxContent>
        <ComboboxEmpty>No matching person</ComboboxEmpty>
        <ComboboxList>
          {(person: PersonResponse) => (
            <ComboboxItem key={person.id} value={person}>
              {person.name}
            </ComboboxItem>
          )}
        </ComboboxList>
      </ComboboxContent>
    </Combobox>
  );
}
