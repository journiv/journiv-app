import type {
  ImmichPeopleImportItem,
  ImmichPeopleImportResult,
  ImmichPersonResponse,
} from "../../../api/generated/types.gen";

/**
 * Pure helpers for the "Import people from Immich" dialog. The dialog holds a
 * `PersonRowState` per Immich person and turns the selected rows into one
 * `ImmichPeopleImportRequest`. Kept framework-free so the mapping rules are
 * unit-tested without rendering.
 */

/** What the row's mode control is set to. "skip" is the frontend's word for
 *  "don't send this row" — the API's own `ignore` mode is never sent. */
export type RowMode = "create" | "link" | "skip";

export type PersonRowState = {
  mode: RowMode;
  /** The name a `create` will use. Seeded from the Immich person's own name;
   *  editable, and the only source when Immich has no name for the face. */
  name: string;
  /** The Journiv person a `link` attaches to. */
  linkPersonId: string | null;
};

/**
 * The row state an Immich person starts in:
 * - already linked to a Journiv person → "skip" (nothing to do)
 * - has an Immich name → "create", pre-filled with that name
 * - unnamed face cluster → "skip" until the user types a name (M2-D4)
 */
export function defaultRowState(person: ImmichPersonResponse): PersonRowState {
  if (person.mapped_person) {
    return { mode: "skip", name: "", linkPersonId: null };
  }
  const name = person.name?.trim() ?? "";
  return {
    mode: name ? "create" : "skip",
    name,
    linkPersonId: null,
  };
}

/** A row that will contribute a valid item to the import batch. */
export function isRowActionable(
  person: ImmichPersonResponse,
  row: PersonRowState,
): boolean {
  if (person.mapped_person) return false;
  if (row.mode === "skip") return false;
  if (row.mode === "create") return row.name.trim().length > 0;
  return Boolean(row.linkPersonId);
}

/**
 * A row the user has pointed at a real action (create / link) but not finished
 * — an unnamed create, or a link with no person chosen. These block the import
 * so a half-set row is never silently dropped.
 */
export function isRowIncomplete(
  person: ImmichPersonResponse,
  row: PersonRowState,
): boolean {
  if (person.mapped_person || row.mode === "skip") return false;
  return !isRowActionable(person, row);
}

export type ImportEntry = {
  person: ImmichPersonResponse;
  row: PersonRowState;
};

/** The `people[]` payload for `POST /integrations/immich/people/import`. Rows
 *  that are not actionable are left out entirely. */
export function buildImportItems(
  entries: ImportEntry[],
  syncEnabled: boolean,
): ImmichPeopleImportItem[] {
  const items: ImmichPeopleImportItem[] = [];
  for (const { person, row } of entries) {
    if (!isRowActionable(person, row)) continue;
    if (row.mode === "create") {
      items.push({
        external_person_id: person.external_person_id,
        mode: "create",
        name: row.name.trim(),
        sync_enabled: syncEnabled,
      });
    } else {
      items.push({
        external_person_id: person.external_person_id,
        mode: "link",
        person_id: row.linkPersonId ?? undefined,
        sync_enabled: syncEnabled,
      });
    }
  }
  return items;
}

export type ImportOutcome = {
  succeeded: ImmichPeopleImportResult[];
  failed: ImmichPeopleImportResult[];
};

/** Split a partial-success response into what landed and what did not. */
export function partitionResults(
  results: ImmichPeopleImportResult[],
): ImportOutcome {
  const succeeded: ImmichPeopleImportResult[] = [];
  const failed: ImmichPeopleImportResult[] = [];
  for (const result of results) {
    if (result.error) failed.push(result);
    else succeeded.push(result);
  }
  return { succeeded, failed };
}
