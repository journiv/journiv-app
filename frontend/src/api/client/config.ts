import { createClient } from "../generated/client/client.gen";
import { sessionStore } from "../auth/session";
import { toApiError } from "./errors";

let refreshing: Promise<string | null> | undefined;

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

async function refreshAccessToken(baseFetch: typeof fetch) {
  if (refreshing) return refreshing;
  refreshing = (async () => {
    const session = sessionStore.read();
    if (!session) return null;
    const response = await baseFetch(`${apiBaseUrl()}/api/v1/auth/refresh`, {
      method: "POST",
      credentials: "include",
    });
    if (!response.ok) {
      sessionStore.clear();
      return null;
    }
    const body = (await response.json()) as { access_token?: string };
    if (!body.access_token) {
      sessionStore.clear();
      return null;
    }
    sessionStore.write({ ...session, accessToken: body.access_token });
    return body.access_token;
  })().finally(() => {
    refreshing = undefined;
  });
  return refreshing;
}

export async function authenticatedFetch(
  request: RequestInfo | URL,
  init?: RequestInit,
) {
  const baseFetch = globalThis.fetch;
  const retryRequest = request instanceof Request ? request.clone() : request;
  const response = await baseFetch(request, init);
  const url =
    typeof request === "string"
      ? request
      : request instanceof Request
        ? request.url
        : request.toString();
  if (
    response.status !== 401 ||
    url.includes("/auth/login") ||
    url.includes("/auth/refresh")
  )
    return response;
  const token = await refreshAccessToken(baseFetch);
  if (!token) return response;
  const inheritedHeaders =
    init?.headers ?? (request instanceof Request ? request.headers : undefined);
  const headers = new Headers(inheritedHeaders);
  headers.set("Authorization", `Bearer ${token}`);
  return baseFetch(retryRequest, { ...init, headers });
}

export function configureApiClient() {
  const token = sessionStore.read()?.accessToken;
  const client = createClient({
    baseUrl: apiBaseUrl(),
    credentials: "include",
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    fetch: authenticatedFetch,
  });
  // The generated client throws the parsed response body, which carries no
  // status. This is the one place that still has the Response, so it is the one
  // place that can keep it. See `ApiError`.
  client.interceptors.error.use((error, response) =>
    toApiError(error, response),
  );
  return client;
}

export function resetAuthRefreshForTests() {
  refreshing = undefined;
}
