/**
 * Thin promise wrapper around the browser Geolocation API, used by the editor's
 * "Use current location" control.
 *
 * Geolocation is a secure-context API. A self-hosted Journiv reached over plain
 * HTTP on a LAN is not a secure context, so `getCurrentPosition` there fails
 * rather than prompting. That is acceptable **only because** the failure is
 * always surfaced (`geolocationErrorMessage`) and the manual place search is
 * always available — nothing here may fail silently.
 */

export type GeoCoords = { latitude: number; longitude: number };

/** Thrown when the API is not present at all (very old or locked-down browser). */
export class GeolocationUnavailableError extends Error {
  constructor() {
    super("Geolocation is not available in this browser");
    this.name = "GeolocationUnavailableError";
  }
}

export function getCurrentPosition(
  options?: PositionOptions,
): Promise<GeoCoords> {
  return new Promise((resolve, reject) => {
    if (typeof navigator === "undefined" || !navigator.geolocation) {
      reject(new GeolocationUnavailableError());
      return;
    }
    navigator.geolocation.getCurrentPosition(
      (position) =>
        resolve({
          latitude: position.coords.latitude,
          longitude: position.coords.longitude,
        }),
      (error) => reject(error),
      {
        enableHighAccuracy: false,
        timeout: 15_000,
        maximumAge: 60_000,
        ...options,
      },
    );
  });
}

/** A human sentence for any geolocation failure — never a raw error. */
export function geolocationErrorMessage(error: unknown): string {
  if (typeof window !== "undefined" && window.isSecureContext === false) {
    return "Sharing your location needs a secure (https) connection. Search for a place instead.";
  }
  if (error instanceof GeolocationUnavailableError) {
    return "This browser can't share your location. Search for a place instead.";
  }
  // GeolocationPositionError: 1 = permission denied, 2 = position unavailable,
  // 3 = timeout. It is not an `Error`, so match structurally.
  if (typeof error === "object" && error !== null && "code" in error) {
    switch ((error as GeolocationPositionError).code) {
      case 1:
        return "Location permission was denied. You can search for a place instead.";
      case 2:
        return "Your location isn't available right now. Try again, or search for a place.";
      case 3:
        return "Finding your location took too long. Try again.";
    }
  }
  return "Couldn't get your location. Search for a place instead.";
}

/** Fallback label when reverse geocoding yields nothing usable. */
export function coordinateLabel({ latitude, longitude }: GeoCoords): string {
  return `${latitude.toFixed(4)}, ${longitude.toFixed(4)}`;
}
