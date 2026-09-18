import { beforeEach, describe, expect, it, vi } from "vitest";

const registerSW = vi.fn();
vi.mock("virtual:pwa-register", () => ({
  registerSW: (...args: unknown[]) => registerSW(...args),
}));

import {
  activateWaitingServiceWorker,
  getUpdateState,
  registerServiceWorker,
  resetServiceWorkerRegistrationForTests,
  subscribeToUpdateState,
} from "./registerServiceWorker";

describe("registerServiceWorker", () => {
  beforeEach(() => {
    registerSW.mockReset();
    resetServiceWorkerRegistrationForTests();
    // jsdom has no Service Worker API; registerServiceWorker() checks for
    // its presence before calling virtual:pwa-register's registerSW.
    Object.defineProperty(navigator, "serviceWorker", {
      configurable: true,
      value: {},
    });
  });

  it("registers exactly once even if called twice", () => {
    registerSW.mockReturnValue(vi.fn());
    registerServiceWorker();
    registerServiceWorker();
    expect(registerSW).toHaveBeenCalledOnce();
  });

  it("notifies subscribers and flips needRefresh when a new worker is waiting", () => {
    let onNeedRefresh: (() => void) | undefined;
    registerSW.mockImplementation((options: { onNeedRefresh?: () => void }) => {
      onNeedRefresh = options.onNeedRefresh;
      return vi.fn();
    });
    registerServiceWorker();
    const listener = vi.fn();
    subscribeToUpdateState(listener);

    expect(getUpdateState().needRefresh).toBe(false);
    onNeedRefresh?.();

    expect(getUpdateState().needRefresh).toBe(true);
    expect(listener).toHaveBeenCalledOnce();
  });

  it("activateWaitingServiceWorker calls the reload callback with reloadPage=true", async () => {
    const reloadAndActivate = vi.fn(async () => {});
    registerSW.mockReturnValue(reloadAndActivate);
    registerServiceWorker();

    await activateWaitingServiceWorker();

    expect(reloadAndActivate).toHaveBeenCalledWith(true);
  });

  it("activateWaitingServiceWorker is a no-op before registration", async () => {
    await expect(activateWaitingServiceWorker()).resolves.toBeUndefined();
  });
});
