import { afterEach, describe, expect, it, vi } from "vitest";
import { api, filenameFromContentDisposition } from "./api";

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllEnvs();
});

describe("browser authentication contract", () => {
  it.each([
    ["password login", () => api.login("person@example.com", "password")],
    ["OIDC exchange", () => api.oidcExchange("one-time-ticket")],
  ])("identifies the PWA for %s", async (_name, authenticate) => {
    vi.stubEnv("VITE_API_BASE_URL", "https://journiv.test");
    let capturedRequest: Request | undefined;
    vi.stubGlobal(
      "fetch",
      vi.fn(async (request: RequestInfo | URL) => {
        capturedRequest =
          request instanceof Request ? request : new Request(request);
        return Response.json({ access_token: "access-token", user: {} });
      }),
    );

    await authenticate();

    expect(capturedRequest?.headers.get("X-Journiv-Client")).toBe("pwa");
    expect(capturedRequest?.credentials).toBe("include");
  });
});

describe("filenameFromContentDisposition", () => {
  it("decodes an RFC 5987 filename* value", () => {
    expect(
      filenameFromContentDisposition(
        "attachment; filename*=UTF-8''rainy%20morning.pdf",
      ),
    ).toBe("rainy morning.pdf");
  });

  it("decodes an RFC 8187 filename* value with a language tag", () => {
    expect(
      filenameFromContentDisposition(
        "attachment; filename*=UTF-8'en'r%C3%A9sum%C3%A9.pdf",
      ),
    ).toBe("résumé.pdf");
  });

  it("reads a plain ASCII filename= value", () => {
    expect(
      filenameFromContentDisposition(
        'attachment; filename="rainy-morning.pdf"',
      ),
    ).toBe("rainy-morning.pdf");
  });

  it("prefers the extended filename* when both are present", () => {
    expect(
      filenameFromContentDisposition(
        "attachment; filename=\"resume.pdf\"; filename*=UTF-8''r%C3%A9sum%C3%A9.pdf",
      ),
    ).toBe("résumé.pdf");
  });

  it("falls back to the ASCII filename when the extended encoding is malformed", () => {
    expect(
      filenameFromContentDisposition(
        "attachment; filename=\"fallback.pdf\"; filename*=UTF-8''%E0%A4%A.pdf",
      ),
    ).toBe("fallback.pdf");
  });

  it("returns undefined when there is no usable filename", () => {
    expect(filenameFromContentDisposition(null)).toBeUndefined();
    expect(filenameFromContentDisposition("attachment")).toBeUndefined();
  });
});
