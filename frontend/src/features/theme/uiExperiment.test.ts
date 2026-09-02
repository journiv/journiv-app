import { afterEach, describe, expect, it } from "vitest";
import {
  applyUiExperiment,
  readUiExperiment,
  UI_DEFAULT,
  uiExperimentCss,
  writeUiExperiment,
} from "./uiExperiment";

afterEach(() => {
  document.getElementById("journiv-ui-experiment")?.remove();
  try {
    window.localStorage.clear();
  } catch {
    /* ignore */
  }
});

describe("uiExperimentCss", () => {
  it("is empty when every axis is at default", () => {
    expect(uiExperimentCss(UI_DEFAULT)).toBe("");
  });

  it("roomy comfort moves the root radius and field padding only", () => {
    const css = uiExperimentCss({ ...UI_DEFAULT, comfort: "roomy" });
    expect(css).toContain("--radius: 1.25rem;");
    expect(css).toContain('[data-slot="input"]');
    expect(css).toContain('[data-slot="textarea"]');
    expect(css).not.toContain('[data-slot="button"]');
  });

  it("lively hover adds shadow and lift on the row selectors", () => {
    const css = uiExperimentCss({ ...UI_DEFAULT, hover: "lively" });
    expect(css).toContain(".jv-moment:hover");
    expect(css).toContain("box-shadow: var(--shadow-xs);");
    expect(css).toContain("transform: translateY(-1px);");
  });

  it("panes: soft is the shipped no-op, hairlines forces hard seams, airy drops the frame", () => {
    expect(uiExperimentCss({ ...UI_DEFAULT, panes: "soft" })).toBe("");

    const hard = uiExperimentCss({ ...UI_DEFAULT, panes: "hairlines" });
    expect(hard).toContain("border-right-color: var(--border);");
    expect(hard).not.toContain("color-mix");

    const airy = uiExperimentCss({ ...UI_DEFAULT, panes: "airy" });
    expect(airy).toContain("border: 0;");
    expect(airy).toContain("gap: var(--space-2);");
  });
});

describe("applyUiExperiment", () => {
  it("writes one <style> and removes it when reset to default", () => {
    applyUiExperiment({ comfort: "roomy", hover: "lively", panes: "airy" });
    const el = document.getElementById("journiv-ui-experiment");
    expect(el).toBeInstanceOf(HTMLStyleElement);
    expect(el?.textContent).toContain("--radius: 1.25rem;");

    applyUiExperiment(UI_DEFAULT);
    expect(document.getElementById("journiv-ui-experiment")).toBeNull();
  });
});

describe("readUiExperiment", () => {
  it("round-trips through storage and falls back on junk", () => {
    writeUiExperiment({ comfort: "roomy", hover: "flat", panes: "hairlines" });
    expect(readUiExperiment()).toEqual({
      comfort: "roomy",
      hover: "flat",
      panes: "hairlines",
    });

    window.localStorage.setItem("journiv.uiExperiment", "{not json");
    expect(readUiExperiment()).toEqual(UI_DEFAULT);
  });
});
