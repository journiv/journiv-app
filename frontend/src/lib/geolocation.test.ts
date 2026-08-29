import { afterEach, describe, expect, it } from "vitest";
import {
  coordinateLabel,
  geolocationErrorMessage,
  GeolocationUnavailableError,
  getCurrentPosition,
} from "./geolocation";

afterEach(() => {
  Reflect.deleteProperty(navigator, "geolocation");
  Reflect.deleteProperty(window, "isSecureContext");
});

function stub(getCurrentPosition: unknown) {
  Object.defineProperty(navigator, "geolocation", {
    configurable: true,
    value: { getCurrentPosition },
  });
}

describe("getCurrentPosition", () => {
  it("resolves plain coordinates from the browser position", async () => {
    stub((ok: (p: unknown) => void) =>
      ok({ coords: { latitude: 51.5, longitude: -0.12, accuracy: 10 } }),
    );
    await expect(getCurrentPosition()).resolves.toEqual({
      latitude: 51.5,
      longitude: -0.12,
    });
  });

  it("rejects with GeolocationUnavailableError when the API is absent", async () => {
    await expect(getCurrentPosition()).rejects.toBeInstanceOf(
      GeolocationUnavailableError,
    );
  });

  it("passes through the browser's own position error", async () => {
    const failure = { code: 3, message: "timeout" };
    stub((_ok: unknown, err: (e: unknown) => void) => err(failure));
    await expect(getCurrentPosition()).rejects.toBe(failure);
  });
});

describe("geolocationErrorMessage", () => {
  it("explains an insecure context before anything else", () => {
    Object.defineProperty(window, "isSecureContext", {
      configurable: true,
      value: false,
    });
    expect(geolocationErrorMessage({ code: 1 })).toMatch(/secure \(https\)/i);
  });

  it("maps the standard position-error codes to sentences", () => {
    expect(geolocationErrorMessage({ code: 1 })).toMatch(
      /permission was denied/i,
    );
    expect(geolocationErrorMessage({ code: 2 })).toMatch(/isn't available/i);
    expect(geolocationErrorMessage({ code: 3 })).toMatch(/too long/i);
  });

  it("handles a missing API and unknown failures", () => {
    expect(geolocationErrorMessage(new GeolocationUnavailableError())).toMatch(
      /can't share your location/i,
    );
    expect(geolocationErrorMessage(new Error("weird"))).toMatch(
      /couldn't get your location/i,
    );
  });
});

describe("coordinateLabel", () => {
  it("formats to four decimal places", () => {
    expect(coordinateLabel({ latitude: 12.34567, longitude: -8.2 })).toBe(
      "12.3457, -8.2000",
    );
  });
});
