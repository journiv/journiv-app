import { createClient } from "../generated/client/client.gen";
import { attemptRefresh, sessionStore } from "../auth/session";
import { apiBaseUrl } from "./baseUrl";
import { toApiError } from "./errors";

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
  const result = await attemptRefresh();
  const token = result === "restored" ? sessionStore.getAccessToken() : null;
  if (!token) return response;
  const inheritedHeaders =
    init?.headers ?? (request instanceof Request ? request.headers : undefined);
  const headers = new Headers(inheritedHeaders);
  headers.set("Authorization", `Bearer ${token}`);
  return baseFetch(retryRequest, { ...init, headers });
}

export function configureApiClient() {
  const token = sessionStore.getAccessToken();
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
