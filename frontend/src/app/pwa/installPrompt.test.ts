import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  hasDeferredInstallPrompt,
  isIosSafari,
  isStandalone,
  promptInstall,
  resetInstallPromptForTests,
  subscribeToInstallPrompt,
} from "./installPrompt";

function stubUserAgent(ua: string) {
  vi.stubGlobal("navigator", {
    ...navigator,
    userAgent: ua,
    standalone: undefined,
  });
}

function fireBeforeInstallPrompt() {
  const event = new Event("beforeinstallprompt", {
    cancelable: true,
  }) as Event & {
    prompt: () => Promise<void>;
    userChoice: Promise<{
      outcome: "accepted" | "dismissed";
      platform: string;
    }>;
  };
  event.prompt = vi.fn(async () => {});
  event.userChoice = Promise.resolve({ outcome: "accepted", platform: "web" });
  window.dispatchEvent(event);
  return event;
}

describe("installPrompt", () => {
  beforeEach(() => {
    resetInstallPromptForTests();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("captures beforeinstallprompt and prevents the default mini-infobar", () => {
    expect(hasDeferredInstallPrompt()).toBe(false);
    const event = fireBeforeInstallPrompt();
    expect(event.defaultPrevented).toBe(true);
    expect(hasDeferredInstallPrompt()).toBe(true);
  });

  it("notifies subscribers when the prompt becomes available", () => {
    const listener = vi.fn();
    subscribeToInstallPrompt(listener);
    fireBeforeInstallPrompt();
    expect(listener).toHaveBeenCalled();
  });

  it("promptInstall shows the captured prompt and clears it (single use)", async () => {
    const event = fireBeforeInstallPrompt();
    const outcome = await promptInstall();
    expect(event.prompt).toHaveBeenCalledOnce();
    expect(outcome).toBe("accepted");
    expect(hasDeferredInstallPrompt()).toBe(false);
  });

  it("promptInstall resolves unavailable when nothing was captured", async () => {
    const outcome = await promptInstall();
    expect(outcome).toBe("unavailable");
  });

  it("clears the deferred prompt on appinstalled", () => {
    fireBeforeInstallPrompt();
    expect(hasDeferredInstallPrompt()).toBe(true);
    window.dispatchEvent(new Event("appinstalled"));
    expect(hasDeferredInstallPrompt()).toBe(false);
  });

  it("isStandalone reads display-mode: standalone", () => {
    vi.spyOn(window, "matchMedia").mockImplementation(
      (query: string) =>
        ({
          matches: query === "(display-mode: standalone)",
        }) as MediaQueryList,
    );
    expect(isStandalone()).toBe(true);
  });

  it("isStandalone reads iOS's navigator.standalone", () => {
    vi.spyOn(window, "matchMedia").mockImplementation(
      () => ({ matches: false }) as MediaQueryList,
    );
    vi.stubGlobal("navigator", { ...navigator, standalone: true });
    expect(isStandalone()).toBe(true);
  });

  it("isIosSafari identifies iOS Safari but not Chrome on iOS", () => {
    stubUserAgent(
      "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/604.1",
    );
    expect(isIosSafari()).toBe(true);

    stubUserAgent(
      "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) CriOS/117.0 Mobile/15E148 Safari/604.1",
    );
    expect(isIosSafari()).toBe(false);
  });

  it("isIosSafari identifies touch-capable iPadOS with a macOS user agent", () => {
    vi.stubGlobal("navigator", {
      ...navigator,
      userAgent:
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
      platform: "MacIntel",
      maxTouchPoints: 5,
    });

    expect(isIosSafari()).toBe(true);
  });

  it("isIosSafari is false on Android Chrome", () => {
    stubUserAgent(
      "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0 Mobile Safari/537.36",
    );
    expect(isIosSafari()).toBe(false);
  });
});
