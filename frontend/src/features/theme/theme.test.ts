import { afterEach, describe, expect, it } from "vitest";
import { applyUserTheme } from "./applyUserTheme";
import amberMinimal from "./__fixtures__/amber-minimal.txt?raw";
import claude from "./__fixtures__/claude.txt?raw";
import modernMinimal from "./__fixtures__/modern-minimal.txt?raw";
import t3Chat from "./__fixtures__/t3-chat.txt?raw";
import { parseThemeCss, ThemeParseError } from "./parseThemeCss";
import { clearUserTheme, readUserTheme, writeUserTheme } from "./themeStorage";
import type { UserTheme } from "./types";

const FIXTURES: Record<string, string> = {
  "amber-minimal": amberMinimal,
  "modern-minimal": modernMinimal,
  claude,
  "t3-chat": t3Chat,
};

afterEach(() => {
  document.getElementById("journiv-user-theme")?.remove();
  clearUserTheme();
});

describe("parseThemeCss — real tweakcn exports", () => {
  for (const [name, css] of Object.entries(FIXTURES)) {
    it(`extracts light + dark colour tokens from "${name}"`, () => {
      const { light, dark, notes } = parseThemeCss(css);
      expect(Object.keys(light).length).toBeGreaterThan(8);
      expect(Object.keys(dark).length).toBeGreaterThan(8);
      // Core tokens always present.
      expect(light.background).toBeTruthy();
      expect(light.primary).toBeTruthy();
      expect(dark.background).toBeTruthy();
      // Font vars are never adopted from CSS.
      expect(light).not.toHaveProperty("font-sans");
      expect(notes.some((n) => n.includes("font"))).toBe(true);
      // Only allowlisted names.
      for (const key of [...Object.keys(light), ...Object.keys(dark)]) {
        expect(key).not.toMatch(/^(tracking|spacing|letter)/);
      }
    });
  }
});

describe("parseThemeCss — leniency and safety", () => {
  it("ignores unknown selectors, @theme and @layer without failing", () => {
    const css = `
      @layer base { :root { --primary: oklch(0.5 0.2 20); } }
      @theme inline { --color-primary: var(--primary); }
      .some-component { color: red; }
      @custom-variant dark (&:is(.dark *));
      .dark { --primary: oklch(0.7 0.2 20); }
    `;
    const { light, dark } = parseThemeCss(css);
    expect(light.primary).toBe("oklch(0.5 0.2 20)");
    expect(dark.primary).toBe("oklch(0.7 0.2 20)");
  });

  it("drops url(), @import lines and unbalanced values with a note but keeps the rest", () => {
    const css = `
      @import "https://evil.example/x.css";
      :root {
        --primary: oklch(0.5 0.2 20);
        --background: url(https://tracker.example/pixel.png);
        --foreground: rgb(0,0,0);
        --card: oklch(0.9 0 0
        --border: expression(alert(1));
      }
    `;
    const { light, notes } = parseThemeCss(css);
    expect(light.primary).toBe("oklch(0.5 0.2 20)");
    expect(light.foreground).toBe("rgb(0,0,0)");
    expect(light).not.toHaveProperty("background");
    expect(light).not.toHaveProperty("border");
    expect(notes.filter((n) => n.includes("Dropped")).length).toBeGreaterThan(
      0,
    );
  });

  it("ignores imported --font-* with an explanatory note", () => {
    const { light, notes } = parseThemeCss(
      `:root { --primary: oklch(0.5 0.2 20); --font-sans: "Comic Sans MS"; }`,
    );
    expect(light).not.toHaveProperty("font-sans");
    expect(notes.some((n) => /font/i.test(n))).toBe(true);
  });

  it("rejects a paste with nothing usable", () => {
    expect(() => parseThemeCss(`.button { color: hotpink; }`)).toThrow(
      ThemeParseError,
    );
    expect(() => parseThemeCss("")).toThrow(ThemeParseError);
  });

  // Prove the value grammar is load-bearing: without it, the url() fixture leaks.
  it("value grammar actually blocks url() — regression guard", () => {
    const css = `:root { --background: url(https://x/y.png); --primary: oklch(0.5 0.2 20); }`;
    const { light } = parseThemeCss(css);
    expect(light.background).toBeUndefined();
  });
});

describe("applyUserTheme", () => {
  const theme: UserTheme = {
    version: 1,
    light: { primary: "oklch(0.5 0.2 20)", border: "oklch(0.9 0 0)" },
    dark: { primary: "oklch(0.7 0.2 20)" },
    systemFont: "lora",
    editorFont: "dm-sans",
    editorFontScale: 1.1,
  };

  it("writes exactly one <style>, both blocks, fonts and prose scale", () => {
    applyUserTheme(theme);
    const el = document.getElementById("journiv-user-theme");
    expect(el).toBeInstanceOf(HTMLStyleElement);
    const css = el?.textContent ?? "";
    expect(css).toContain(":root {");
    expect(css).toContain("--primary: oklch(0.5 0.2 20);");
    expect(css).toContain("--border: oklch(0.9 0 0);");
    expect(css).toContain(".dark {");
    expect(css).toContain("--prose-font-scale: 1.1;");
    expect(css).toMatch(/--font-sans: "Lora Variable"/);
    expect(css).toMatch(/--font-reader: "DM Sans Variable"/);
    // Never touches the document root font-size.
    expect(css).not.toMatch(/font-size/);
  });

  it("replaces the style on re-apply and removes it for an empty theme", () => {
    applyUserTheme(theme);
    applyUserTheme({ ...theme, light: { primary: "oklch(0.4 0.2 20)" } });
    expect(document.querySelectorAll("#journiv-user-theme").length).toBe(1);
    expect(
      document.getElementById("journiv-user-theme")?.textContent,
    ).toContain("oklch(0.4 0.2 20)");
    applyUserTheme({ version: 1, light: {}, dark: {} });
    expect(document.getElementById("journiv-user-theme")).toBeNull();
  });
});

describe("themeStorage", () => {
  it("round-trips a UserTheme", () => {
    const theme: UserTheme = {
      version: 1,
      light: { primary: "oklch(0.5 0.2 20)" },
      dark: {},
      systemFont: "lora",
      editorFontScale: 1.05,
    };
    writeUserTheme(theme);
    expect(readUserTheme()).toEqual(theme);
  });

  it("tolerates absent and corrupt storage", () => {
    expect(readUserTheme()).toEqual({ version: 1, light: {}, dark: {} });
    window.localStorage.setItem("journiv.userTheme", "{not json");
    expect(readUserTheme()).toEqual({ version: 1, light: {}, dark: {} });
  });

  it("strips unknown keys and out-of-range values on read", () => {
    window.localStorage.setItem(
      "journiv.userTheme",
      JSON.stringify({
        version: 1,
        light: { primary: "oklch(0.5 0.2 20)", evil: "x", "font-sans": "y" },
        dark: {},
        systemFont: "not-a-font",
        editorFontScale: 99,
      }),
    );
    const t = readUserTheme();
    expect(t.light).toEqual({ primary: "oklch(0.5 0.2 20)" });
    expect(t.systemFont).toBeUndefined();
    expect(t.editorFontScale).toBeUndefined();
  });
});
