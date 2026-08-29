import { describe, expect, it } from "vitest";
import { isExplicitSaveShortcut } from "./shortcuts";

const event = (overrides: Partial<KeyboardEvent> = {}) =>
  ({
    altKey: false,
    ctrlKey: false,
    isComposing: false,
    key: "s",
    metaKey: false,
    ...overrides,
  }) as KeyboardEvent;

describe("editor shortcuts", () => {
  it("recognizes Command/Ctrl+S", () => {
    expect(isExplicitSaveShortcut(event({ metaKey: true }))).toBe(true);
    expect(isExplicitSaveShortcut(event({ ctrlKey: true, key: "S" }))).toBe(
      true,
    );
  });

  it("does not interrupt composition or alternate shortcuts", () => {
    expect(
      isExplicitSaveShortcut(event({ metaKey: true, isComposing: true })),
    ).toBe(false);
    expect(isExplicitSaveShortcut(event({ ctrlKey: true, altKey: true }))).toBe(
      false,
    );
    expect(isExplicitSaveShortcut(event({ metaKey: true, key: "x" }))).toBe(
      false,
    );
  });
});
