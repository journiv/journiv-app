import { QueryClientProvider } from "@tanstack/react-query";
import { createMemoryHistory, RouterProvider } from "@tanstack/react-router";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { sessionStore } from "../../../api/auth/session";
import { api } from "../../../api/client/api";
import type {
  InstanceConfigResponse,
  IntegrationStatusResponse,
} from "../../../api/generated/types.gen";
import { createAppQueryClient } from "../../../app/queryClient";
import { createAppRouter } from "../../../app/router";
import { setTestViewportWidth } from "../../../test/viewport";

vi.mock("../../../api/client/api", () => ({
  api: {
    me: vi.fn(),
    instanceConfig: vi.fn(),
    integrationStatus: vi.fn(),
    connectImmich: vi.fn(),
    updateImmich: vi.fn(),
    disconnectImmich: vi.fn(),
    syncImmich: vi.fn(),
    journals: vi.fn(),
    moments: vi.fn(),
  },
}));

const now = "2026-08-27T09:00:00Z";

const configWithImmich: InstanceConfigResponse = {
  import_export_max_file_size_mb: 100,
  max_file_size_mb: 50,
  disable_signup: false,
  oidc_enabled: false,
  oidc_only: false,
  immich_base_url: "https://photos.example.com",
  plus: {
    available: false,
    tier: "member",
    upgrade_url: "https://journiv.com/plus",
  },
};

const disconnected: IntegrationStatusResponse = {
  provider: "immich",
  status: "disconnected",
  import_mode: "link_only",
};

const connected: IntegrationStatusResponse = {
  provider: "immich",
  status: "connected",
  is_active: true,
  external_user_id: "immich-user-9",
  connected_at: now,
  last_synced_at: now,
  import_mode: "link_only",
};

beforeEach(() => {
  vi.clearAllMocks();
  sessionStorage.clear();
  sessionStore.write({ version: 1, accessToken: "a", refreshToken: "r" });
  vi.mocked(api.me).mockResolvedValue({
    id: "user-1",
    email: "writer@example.com",
    name: "Writer",
    role: "user",
    is_active: true,
    is_oidc_user: false,
    created_at: now,
    updated_at: now,
  });
  vi.mocked(api.instanceConfig).mockResolvedValue(configWithImmich);
  vi.mocked(api.integrationStatus).mockResolvedValue(disconnected);
  vi.mocked(api.connectImmich).mockResolvedValue({
    status: "connected",
    provider: "immich",
    external_user_id: "immich-user-9",
    connected_at: now,
  });
  vi.mocked(api.updateImmich).mockResolvedValue(connected);
  vi.mocked(api.disconnectImmich).mockResolvedValue(undefined as never);
  vi.mocked(api.syncImmich).mockResolvedValue({
    status: "accepted",
    message: "Sync started",
  } as never);
  vi.mocked(api.journals).mockResolvedValue([]);
  vi.mocked(api.moments).mockResolvedValue({ items: [] });
});

async function view(path = "/settings/integrations") {
  const router = createAppRouter(
    createMemoryHistory({ initialEntries: [path] }),
  );
  const queryClient = createAppQueryClient();
  queryClient.setDefaultOptions({ queries: { retry: false } });
  render(
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
  await router.load();
  return { page: within(await screen.findByRole("dialog")), router };
}

/** Straight to the Immich detail — the form that used to live at
 *  `/settings/integrations`. */
const detail = () => view("/settings/integrations/immich");

/** The catalogue row's own link (not the "setup guide" link that shares the
 *  word "Immich"), found by its destination. */
function immichRowLink(page: ReturnType<typeof within>) {
  return page
    .queryAllByRole("link")
    .find((link: HTMLElement) =>
      link.getAttribute("href")?.includes("/settings/integrations/immich"),
    );
}

describe("Settings · Integrations · catalogue", () => {
  it("lists Immich as a linked row with a status pill and a setup guide", async () => {
    const { page } = await view();
    await page.findByText("Immich");

    const link = immichRowLink(page);
    expect(link?.getAttribute("href")).toContain(
      "/settings/integrations/immich",
    );
    const row = link?.closest("li") as HTMLElement;

    // Status pill: not connected yet.
    expect(within(row).getByText("Not connected")).toBeTruthy();

    // Setup guide opens the public docs in a new tab.
    const guide = within(row).getByRole("link", { name: "Immich setup guide" });
    expect(guide.getAttribute("href")).toBe(
      "https://www.journiv.com/docs/guides/immich-integration",
    );
    expect(guide.getAttribute("target")).toBe("_blank");
    expect(guide.getAttribute("rel")).toContain("noreferrer");

    // The "more coming" row is present and inert.
    expect(page.getByText("More integrations")).toBeTruthy();
  });

  it("shows Immich as unavailable and unlinked when the instance has no server", async () => {
    vi.mocked(api.instanceConfig).mockResolvedValue({
      ...configWithImmich,
      immich_base_url: undefined,
    });
    const { page } = await view();

    expect(await page.findByText("Immich")).toBeTruthy();
    expect(immichRowLink(page)).toBeUndefined();
    expect(page.getByText("Not available")).toBeTruthy();
    expect(page.getByText("Not enabled on this instance.")).toBeTruthy();
  });

  it("reflects a live connection in the pill", async () => {
    vi.mocked(api.integrationStatus).mockResolvedValue(connected);
    const { page } = await view();
    expect(await page.findByText("Connected")).toBeTruthy();
  });

  it("flags a provider error in the pill", async () => {
    vi.mocked(api.integrationStatus).mockResolvedValue({
      ...connected,
      last_error: "401 Unauthorized",
    });
    const { page } = await view();
    expect(await page.findByText("Attention needed")).toBeTruthy();
  });

  it("says the status is unavailable when the status request fails", async () => {
    vi.mocked(api.integrationStatus).mockRejectedValue(new Error("offline"));
    const { page } = await view();
    // Catalogue still renders; the pill degrades rather than erroring the page.
    expect(await page.findByText("Status unavailable")).toBeTruthy();
    expect(immichRowLink(page)?.getAttribute("href")).toContain(
      "/settings/integrations/immich",
    );
  });

  it("opens the detail when the row is clicked", async () => {
    const { page, router } = await view();
    await page.findByText("Immich");
    await userEvent.click(immichRowLink(page) as HTMLElement);
    await waitFor(() =>
      expect(router.state.location.pathname).toBe(
        "/settings/integrations/immich",
      ),
    );
    expect(await page.findByLabelText("API key")).toBeTruthy();
  });

  it("redirects an unknown provider sub-route back to the catalogue", async () => {
    const { page, router } = await view("/settings/integrations/dropbox");
    await waitFor(() =>
      expect(router.state.location.pathname).toBe("/settings/integrations"),
    );
    expect(await page.findByText("More integrations")).toBeTruthy();
  });
});

describe("Settings · Integrations · Immich detail", () => {
  it("deep-links to the form with Providers still marked active", async () => {
    const { page } = await detail();
    expect(await page.findByLabelText("API key")).toBeTruthy();
    expect(
      page
        .getByRole("link", { name: "Providers" })
        .getAttribute("aria-current"),
    ).toBe("page");
  });

  it("returns to the catalogue from the back control", async () => {
    const { page, router } = await detail();
    await page.findByLabelText("API key");
    await userEvent.click(
      page.getAllByRole("link", { name: /back to integrations/i })[0],
    );
    await waitFor(() =>
      expect(router.state.location.pathname).toBe("/settings/integrations"),
    );
    expect(await page.findByText("More integrations")).toBeTruthy();
  });

  it("shows a not-enabled state when the instance has no Immich server", async () => {
    vi.mocked(api.instanceConfig).mockResolvedValue({
      ...configWithImmich,
      immich_base_url: undefined,
    });
    const { page } = await detail();
    expect(
      await page.findByText("Immich isn’t enabled on this instance"),
    ).toBeTruthy();
    expect(page.queryByLabelText("API key")).toBeNull();
  });

  it("connects with the chosen import mode and refreshes status", async () => {
    vi.mocked(api.integrationStatus)
      .mockResolvedValueOnce(disconnected)
      .mockResolvedValue(connected);
    const { page } = await detail();

    const key = (await page.findByLabelText("API key")) as HTMLInputElement;
    const connect = page.getByRole("button", { name: "Connect" });
    expect((connect as HTMLButtonElement).disabled).toBe(true);

    await userEvent.type(key, "immich-key-123");
    await userEvent.click(
      page.getByRole("radio", { name: /Copy into Journiv/ }),
    );
    expect((connect as HTMLButtonElement).disabled).toBe(false);
    await userEvent.click(connect);

    await waitFor(() =>
      expect(api.connectImmich).toHaveBeenCalledWith(
        { api_key: "immich-key-123" },
        "copy",
      ),
    );
    await waitFor(() =>
      expect(page.getAllByText("Connected").length).toBeGreaterThan(0),
    );
  });

  it("keeps a typed key and reports a failed connect", async () => {
    vi.mocked(api.connectImmich).mockRejectedValueOnce(new Error("bad key"));
    const { page } = await detail();
    const key = (await page.findByLabelText("API key")) as HTMLInputElement;
    await userEvent.type(key, "wrong-key");
    await userEvent.click(page.getByRole("button", { name: "Connect" }));

    expect((await page.findByRole("alert")).textContent).toContain(
      "couldn’t be saved",
    );
    expect(key.value).toBe("wrong-key");
  });

  it("changes the import mode on a live connection", async () => {
    vi.mocked(api.integrationStatus).mockResolvedValue(connected);
    const { page } = await detail();

    const save = await page.findByRole("button", { name: "Save settings" });
    expect((save as HTMLButtonElement).disabled).toBe(true);
    expect(page.queryByLabelText("API key")).toBeNull();

    await userEvent.click(
      page.getByRole("radio", { name: /Copy into Journiv/ }),
    );
    expect((save as HTMLButtonElement).disabled).toBe(false);
    await userEvent.click(save);

    await waitFor(() =>
      expect(api.updateImmich).toHaveBeenCalledWith({ import_mode: "copy" }),
    );
  });

  it("triggers a manual sync", async () => {
    vi.mocked(api.integrationStatus).mockResolvedValue(connected);
    const { page } = await detail();
    await userEvent.click(
      await page.findByRole("button", { name: "Sync now" }),
    );
    await waitFor(() => expect(api.syncImmich).toHaveBeenCalledTimes(1));
    expect(await page.findByText(/Sync started/)).toBeTruthy();
  });

  it("confirms before disconnecting", async () => {
    vi.mocked(api.integrationStatus).mockResolvedValue(connected);
    const { page } = await detail();
    await userEvent.click(
      await page.findByRole("button", { name: "Disconnect" }),
    );
    const dialog = await screen
      .findByRole("alertdialog")
      .catch(() => screen.getByRole("dialog", { name: "Disconnect Immich?" }));
    await userEvent.click(
      within(dialog as HTMLElement).getByRole("button", { name: "Disconnect" }),
    );
    await waitFor(() => expect(api.disconnectImmich).toHaveBeenCalledTimes(1));
  });

  it("confirms disconnect in a compact bottom sheet", async () => {
    setTestViewportWidth(390);
    vi.mocked(api.integrationStatus).mockResolvedValue(connected);
    const { page } = await detail();
    await userEvent.click(
      await page.findByRole("button", { name: "Disconnect" }),
    );
    const dialog = await screen.findByRole("dialog", {
      name: "Disconnect Immich?",
    });
    expect(dialog.dataset.slot).toBe("drawer-popup");
  });

  it("offers the key field again when the provider reports an error", async () => {
    vi.mocked(api.integrationStatus).mockResolvedValue({
      ...connected,
      last_error: "401 Unauthorized",
    });
    const { page } = await detail();
    expect(
      (await page.findAllByRole("alert")).some((node) =>
        node.textContent?.includes("connection problem"),
      ),
    ).toBe(true);
    expect(page.getByLabelText("API key")).toBeTruthy();
  });

  it("reconnects with a replacement key after the provider reports an error", async () => {
    vi.mocked(api.integrationStatus).mockResolvedValue({
      ...connected,
      last_error: "401 Unauthorized",
    });
    const { page } = await detail();
    const key = (await page.findByLabelText("API key")) as HTMLInputElement;
    const save = page.getByRole("button", { name: "Save settings" });

    expect((save as HTMLButtonElement).disabled).toBe(true);
    await userEvent.type(key, " replacement-key ");
    expect((save as HTMLButtonElement).disabled).toBe(false);
    await userEvent.click(save);

    await waitFor(() =>
      expect(api.connectImmich).toHaveBeenCalledWith(
        { api_key: "replacement-key" },
        "link_only",
      ),
    );
    expect(api.updateImmich).not.toHaveBeenCalled();
  });

  it("guards an unsaved key when switching settings sections", async () => {
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
    const { page, router } = await detail();
    await userEvent.type(await page.findByLabelText("API key"), "half-typed");
    await userEvent.click(page.getByRole("link", { name: "Profile" }));
    expect(confirm).toHaveBeenCalled();
    expect(router.state.location.pathname).toBe(
      "/settings/integrations/immich",
    );
    confirm.mockRestore();
  });
});
