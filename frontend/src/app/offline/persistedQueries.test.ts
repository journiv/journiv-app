import { describe, expect, it } from "vitest";
import { queryKeys } from "../../api/query/keys";
import {
  MAX_AGE_MS,
  type PersistableQuery,
  shouldPersistQuery,
} from "./persistedQueries";

function successfulQuery(
  queryKey: readonly unknown[],
  overrides: Partial<PersistableQuery["state"]> = {},
): PersistableQuery {
  return {
    queryKey,
    state: {
      status: "success",
      data: { ok: true },
      dataUpdatedAt: Date.now(),
      ...overrides,
    },
  };
}

describe("shouldPersistQuery", () => {
  it("accepts every key in the allowlist", () => {
    const allowlisted: (readonly unknown[])[] = [
      queryKeys.me,
      queryKeys.userSettings,
      queryKeys.instanceConfig,
      queryKeys.journals,
      queryKeys.tags,
      queryKeys.people,
      queryKeys.moods,
      queryKeys.activities,
      queryKeys.goals,
      queryKeys.moments({}),
      queryKeys.moment("moment-1"),
    ];
    for (const key of allowlisted) {
      expect(
        shouldPersistQuery(successfulQuery(key)),
        JSON.stringify(key),
      ).toBe(true);
    }
  });

  it("rejects export, integrations, and admin queries", () => {
    expect(
      shouldPersistQuery(successfulQuery(queryKeys.exportJob("job-1"))),
    ).toBe(false);
    expect(shouldPersistQuery(successfulQuery(queryKeys.exportJobs))).toBe(
      false,
    );
    expect(
      shouldPersistQuery(
        successfulQuery(queryKeys.integrationStatus("immich")),
      ),
    ).toBe(false);
    expect(shouldPersistQuery(successfulQuery(queryKeys.adminUsers))).toBe(
      false,
    );
    expect(
      shouldPersistQuery(successfulQuery(queryKeys.promptLibrary({}))),
    ).toBe(false);
  });

  it("rejects a filtered moments query -- only the unfiltered timeline persists", () => {
    expect(
      shouldPersistQuery(successfulQuery(queryKeys.moments({ tag_id: "x" }))),
    ).toBe(false);
  });

  it("rejects moment media -- offline media viewing is out of scope", () => {
    expect(
      shouldPersistQuery(successfulQuery(queryKeys.momentMedia("m1"))),
    ).toBe(false);
  });

  it("rejects a query that has not succeeded yet", () => {
    expect(
      shouldPersistQuery(
        successfulQuery(queryKeys.journals, {
          status: "pending",
          data: undefined,
        }),
      ),
    ).toBe(false);
    expect(
      shouldPersistQuery(
        successfulQuery(queryKeys.journals, { status: "error" }),
      ),
    ).toBe(false);
  });

  it("rejects data older than MAX_AGE_MS", () => {
    expect(
      shouldPersistQuery(
        successfulQuery(queryKeys.journals, {
          dataUpdatedAt: Date.now() - MAX_AGE_MS - 1000,
        }),
      ),
    ).toBe(false);
  });
});
