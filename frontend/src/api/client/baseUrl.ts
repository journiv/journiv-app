function isLoopbackHostname(hostname: string) {
  const normalized = hostname.toLowerCase();
  const octets = normalized.split(".");
  const isIpv4Loopback =
    octets.length === 4 &&
    octets[0] === "127" &&
    octets.every((octet) => /^\d{1,3}$/.test(octet) && Number(octet) <= 255);
  return (
    normalized === "localhost" ||
    isIpv4Loopback ||
    normalized === "[::1]" ||
    normalized === "::1"
  );
}

function validateCredentialedApiBaseUrl(baseUrl: string) {
  if (!baseUrl) return;

  const pageOrigin = globalThis.location?.origin;
  let parsed: URL;
  try {
    parsed = new URL(baseUrl, pageOrigin ?? "http://localhost");
  } catch {
    throw new Error("VITE_API_BASE_URL must be a valid URL");
  }

  if (
    parsed.protocol === "http:" &&
    !isLoopbackHostname(parsed.hostname) &&
    (!pageOrigin || parsed.origin !== pageOrigin)
  ) {
    throw new Error(
      "VITE_API_BASE_URL must use HTTPS for credentialed cross-origin requests; " +
        "HTTP is allowed only for loopback or a same-origin server configured with " +
        "ALLOW_INSECURE_COOKIE_AUTH_OVER_HTTP=true",
    );
  }
}

export function apiBaseUrl() {
  const baseUrl = import.meta.env.VITE_API_BASE_URL ?? "";
  validateCredentialedApiBaseUrl(baseUrl);
  return baseUrl;
}
