import { describe, expect, it } from "vitest";
import { shouldClearMediaParam } from "./mediaViewerNav";

describe("shouldClearMediaParam", () => {
  it("never clears when there is no media param", () => {
    expect(
      shouldClearMediaParam({
        mediaParam: undefined,
        settled: true,
        hasItem: false,
      }),
    ).toBe(false);
  });

  it("does not clear a valid deep link while the list is still loading", () => {
    // The moment media query has not resolved yet, so an unknown id is
    // not-loaded-yet, not stale.
    expect(
      shouldClearMediaParam({
        mediaParam: "abc",
        settled: false,
        hasItem: false,
      }),
    ).toBe(false);
  });

  it("keeps the param once the list has loaded and contains the id", () => {
    expect(
      shouldClearMediaParam({
        mediaParam: "abc",
        settled: true,
        hasItem: true,
      }),
    ).toBe(false);
  });

  it("clears the param once the list has loaded without the id", () => {
    expect(
      shouldClearMediaParam({
        mediaParam: "abc",
        settled: true,
        hasItem: false,
      }),
    ).toBe(true);
  });
});
