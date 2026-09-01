import { describe, expect, it } from "vitest";
import type {
  ImmichPeopleImportResult,
  ImmichPersonResponse,
} from "../../../api/generated/types.gen";
import {
  buildImportItems,
  defaultRowState,
  type ImportEntry,
  isRowActionable,
  isRowIncomplete,
  partitionResults,
  type PersonRowState,
} from "./immichPeopleImport";

const person = (
  over: Partial<ImmichPersonResponse> = {},
): ImmichPersonResponse => ({
  external_person_id: "ext-1",
  name: "Ada Lovelace",
  thumbnail_url:
    "/api/v1/integrations/immich/proxy/people/ext-1/thumbnail?sig=a",
  is_hidden: false,
  is_favorite: false,
  sync_enabled: false,
  ...over,
});

describe("defaultRowState", () => {
  it("defaults a named, unmapped person to create with the name filled in", () => {
    expect(defaultRowState(person())).toEqual({
      mode: "create",
      name: "Ada Lovelace",
      linkPersonId: null,
    });
  });

  it("defaults an unnamed face cluster to skip with an empty name", () => {
    expect(defaultRowState(person({ name: null }))).toEqual({
      mode: "skip",
      name: "",
      linkPersonId: null,
    });
  });

  it("defaults an already-linked person to skip", () => {
    const mapped = person({
      mapped_person: { id: "p-9", name: "Ada L." },
    });
    expect(defaultRowState(mapped)).toEqual({
      mode: "skip",
      name: "",
      linkPersonId: null,
    });
  });

  it("trims whitespace-only Immich names down to unnamed", () => {
    expect(defaultRowState(person({ name: "   " })).mode).toBe("skip");
  });
});

describe("isRowActionable / isRowIncomplete", () => {
  const row = (over: Partial<PersonRowState> = {}): PersonRowState => ({
    mode: "create",
    name: "Ada",
    linkPersonId: null,
    ...over,
  });

  it("a named create is actionable and complete", () => {
    expect(isRowActionable(person(), row())).toBe(true);
    expect(isRowIncomplete(person(), row())).toBe(false);
  });

  it("a create with a blank name is incomplete, not actionable", () => {
    const r = row({ name: "  " });
    expect(isRowActionable(person({ name: null }), r)).toBe(false);
    expect(isRowIncomplete(person({ name: null }), r)).toBe(true);
  });

  it("a link with a chosen person is actionable", () => {
    const r = row({ mode: "link", linkPersonId: "p-3" });
    expect(isRowActionable(person(), r)).toBe(true);
    expect(isRowIncomplete(person(), r)).toBe(false);
  });

  it("a link with no person chosen is incomplete", () => {
    const r = row({ mode: "link", linkPersonId: null });
    expect(isRowActionable(person(), r)).toBe(false);
    expect(isRowIncomplete(person(), r)).toBe(true);
  });

  it("skip is neither actionable nor incomplete", () => {
    const r = row({ mode: "skip" });
    expect(isRowActionable(person(), r)).toBe(false);
    expect(isRowIncomplete(person(), r)).toBe(false);
  });

  it("an already-mapped person is never actionable, even set to create", () => {
    const mapped = person({ mapped_person: { id: "p-1", name: "Ada" } });
    expect(isRowActionable(mapped, row())).toBe(false);
    expect(isRowIncomplete(mapped, row())).toBe(false);
  });
});

describe("buildImportItems", () => {
  const entry = (
    p: Partial<ImmichPersonResponse>,
    r: Partial<PersonRowState>,
  ): ImportEntry => ({
    person: person(p),
    row: { mode: "create", name: "", linkPersonId: null, ...r },
  });

  it("emits a create item with the trimmed name and the batch sync flag", () => {
    const items = buildImportItems(
      [
        entry(
          { external_person_id: "ext-a" },
          { mode: "create", name: " Ada " },
        ),
      ],
      true,
    );
    expect(items).toEqual([
      {
        external_person_id: "ext-a",
        mode: "create",
        name: "Ada",
        sync_enabled: true,
      },
    ]);
  });

  it("emits a link item carrying the chosen person id", () => {
    const items = buildImportItems(
      [
        entry(
          { external_person_id: "ext-b" },
          { mode: "link", linkPersonId: "p-7" },
        ),
      ],
      false,
    );
    expect(items).toEqual([
      {
        external_person_id: "ext-b",
        mode: "link",
        person_id: "p-7",
        sync_enabled: false,
      },
    ]);
  });

  it("drops skipped, incomplete and already-mapped rows", () => {
    const items = buildImportItems(
      [
        entry({ external_person_id: "skip" }, { mode: "skip" }),
        entry(
          { external_person_id: "blank", name: null },
          { mode: "create", name: "" },
        ),
        entry(
          {
            external_person_id: "mapped",
            mapped_person: { id: "p-1", name: "X" },
          },
          { mode: "create", name: "X" },
        ),
        entry({ external_person_id: "keep" }, { mode: "create", name: "Ada" }),
      ],
      true,
    );
    expect(items.map((item) => item.external_person_id)).toEqual(["keep"]);
  });
});

describe("partitionResults", () => {
  it("splits results by the presence of an error", () => {
    const results: ImmichPeopleImportResult[] = [
      {
        external_person_id: "a",
        mode: "create",
        person: { id: "p1", name: "A" },
      },
      { external_person_id: "b", mode: "link", error: "already linked" },
      {
        external_person_id: "c",
        mode: "create",
        person: { id: "p3", name: "C" },
      },
    ];
    const { succeeded, failed } = partitionResults(results);
    expect(succeeded.map((r) => r.external_person_id)).toEqual(["a", "c"]);
    expect(failed.map((r) => r.external_person_id)).toEqual(["b"]);
  });
});
