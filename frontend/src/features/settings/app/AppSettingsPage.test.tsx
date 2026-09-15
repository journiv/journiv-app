import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { resetInstallPromptForTests } from "../../../app/pwa/installPrompt";
import { AppSettingsPage } from "./AppSettingsPage";

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
}

describe("AppSettingsPage", () => {
  beforeEach(() => {
    resetInstallPromptForTests();
    vi.spyOn(window, "matchMedia").mockImplementation(
      () => ({ matches: false }) as MediaQueryList,
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("shows an honest reason and no button when nothing applies", () => {
    vi.stubGlobal("isSecureContext", true);
    render(<AppSettingsPage />);
    expect(
      screen.getByText(/doesn't currently offer installing/i),
    ).toBeTruthy();
    expect(
      screen.queryByRole("button", { name: /install journiv/i }),
    ).toBeNull();
  });

  it("explains a plain-HTTP deployment honestly rather than a mystery disabled button", () => {
    // jsdom's default test origin is not a secure context, exercising the
    // exact plain-HTTP case this row must explain rather than hide.
    render(<AppSettingsPage />);
    expect(
      screen.getByText(/needs a secure \(https\) connection/i),
    ).toBeTruthy();
    expect(
      screen.queryByRole("button", { name: /install journiv/i }),
    ).toBeNull();
  });

  it("shows an Install button once beforeinstallprompt fires", async () => {
    render(<AppSettingsPage />);
    fireBeforeInstallPrompt();
    expect(
      await screen.findByRole("button", { name: "Install Journiv" }),
    ).toBeTruthy();
  });

  it("shows Share instructions on iOS Safari, no button", () => {
    vi.stubGlobal("navigator", {
      ...navigator,
      userAgent:
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/604.1",
    });
    render(<AppSettingsPage />);
    expect(screen.getByText(/Add to Home Screen/i)).toBeTruthy();
    expect(
      screen.queryByRole("button", { name: /install journiv/i }),
    ).toBeNull();
  });

  it("shows an already-installed state, no button", () => {
    vi.spyOn(window, "matchMedia").mockImplementation(
      (query: string) =>
        ({ matches: query === "(display-mode: standalone)" }) as MediaQueryList,
    );
    render(<AppSettingsPage />);
    expect(screen.getByText(/is installed on this device/i)).toBeTruthy();
    expect(
      screen.queryByRole("button", { name: /install journiv/i }),
    ).toBeNull();
  });
});
