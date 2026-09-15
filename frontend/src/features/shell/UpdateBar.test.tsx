import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

const registerSW = vi.fn();
vi.mock("virtual:pwa-register", () => ({
  registerSW: (...args: unknown[]) => registerSW(...args),
}));

import {
  registerServiceWorker,
  resetServiceWorkerRegistrationForTests,
} from "../../app/pwa/registerServiceWorker";
import { ShellContext, type ShellContextValue } from "./shellContext";
import { UpdateBar } from "./UpdateBar";

function renderUpdateBar(hasUnsavedDraft: boolean) {
  const value: ShellContextValue = {
    openNavigation: () => {},
    openQuickLog: () => {},
    hasUnsavedDraft,
    setHasUnsavedDraft: () => {},
  };
  return render(
    <ShellContext.Provider value={value}>
      <UpdateBar />
    </ShellContext.Provider>,
  );
}

describe("UpdateBar", () => {
  let onNeedRefresh: (() => void) | undefined;
  let reloadAndActivate: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    registerSW.mockReset();
    resetServiceWorkerRegistrationForTests();
    Object.defineProperty(navigator, "serviceWorker", {
      configurable: true,
      value: {},
    });
    reloadAndActivate = vi.fn(async () => {});
    registerSW.mockImplementation((options: { onNeedRefresh?: () => void }) => {
      onNeedRefresh = options.onNeedRefresh;
      return reloadAndActivate;
    });
    registerServiceWorker();
  });

  it("renders nothing until an update is waiting", () => {
    renderUpdateBar(false);
    expect(screen.queryByText(/new version/i)).toBeNull();
  });

  it("restarts immediately when there is no unsaved draft", async () => {
    renderUpdateBar(false);
    onNeedRefresh?.();
    const user = userEvent.setup();

    await user.click(
      await screen.findByRole("button", { name: "Restart to update" }),
    );

    expect(reloadAndActivate).toHaveBeenCalledWith(true);
  });

  it("does not call applyUpdate without confirmation when a draft is dirty", async () => {
    renderUpdateBar(true);
    onNeedRefresh?.();
    const user = userEvent.setup();

    await user.click(
      await screen.findByRole("button", { name: "Restart to update" }),
    );

    expect(reloadAndActivate).not.toHaveBeenCalled();
    expect(
      await screen.findByRole("alertdialog", { name: "Restart to update?" }),
    ).toBeTruthy();

    await user.click(screen.getByRole("button", { name: "Restart" }));
    expect(reloadAndActivate).toHaveBeenCalledWith(true);
  });

  it("dismissal hides the bar without applying the update", async () => {
    renderUpdateBar(false);
    onNeedRefresh?.();
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: "Dismiss" }));

    expect(screen.queryByText(/new version/i)).toBeNull();
    expect(reloadAndActivate).not.toHaveBeenCalled();
  });
});
