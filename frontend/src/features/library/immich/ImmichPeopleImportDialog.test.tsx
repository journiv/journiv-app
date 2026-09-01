import { QueryClientProvider } from "@tanstack/react-query";
import { createMemoryHistory, RouterProvider } from "@tanstack/react-router";
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent, {
  PointerEventsCheckLevel,
} from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { sessionStore } from "../../../api/auth/session";
import { api } from "../../../api/client/api";
import { ApiError } from "../../../api/client/errors";
import type {
  ImmichPeopleImportResponse,
  ImmichPeopleListResponse,
  ImmichPersonResponse,
  InstanceConfigResponse,
  IntegrationStatusResponse,
  PersonResponse,
  UserResponse,
} from "../../../api/generated/types.gen";
import { createAppQueryClient } from "../../../app/queryClient";
import { createAppRouter } from "../../../app/router";
import { setTestViewportWidth } from "../../../test/viewport";

vi.mock("../../../api/client/api", () => ({
  api: {
    me: vi.fn(),
    journals: vi.fn(),
    people: vi.fn(),
    personGroups: vi.fn(),
    createPerson: vi.fn(),
    updatePerson: vi.fn(),
    archivePerson: vi.fn(),
    mergePeople: vi.fn(),
    uploadPersonImage: vi.fn(),
    removePersonImage: vi.fn(),
    createPersonGroup: vi.fn(),
    updatePersonGroup: vi.fn(),
    deletePersonGroup: vi.fn(),
    instanceConfig: vi.fn(),
    integrationStatus: vi.fn(),
    immichPeople: vi.fn(),
    importImmichPeople: vi.fn(),
  },
}));

const now = "2026-08-27T09:00:00Z";

const user: UserResponse = {
  id: "user-1",
  email: "writer@example.com",
  name: "Writer",
  role: "user",
  is_active: true,
  created_at: now,
  updated_at: now,
};

const jane: PersonResponse = {
  id: "person-jane",
  user_id: user.id,
  name: "Jane Doe",
  nickname: "Janie",
  memory_count: 3,
  groups: [],
  created_at: now,
  updated_at: now,
};

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
const configWithoutImmich: InstanceConfigResponse = {
  ...configWithImmich,
  immich_base_url: null,
};

const connected: IntegrationStatusResponse = {
  provider: "immich",
  status: "connected",
  is_active: true,
  import_mode: "link_only",
};
const disconnected: IntegrationStatusResponse = {
  provider: "immich",
  status: "disconnected",
  import_mode: "link_only",
};

const immichPerson = (
  over: Partial<ImmichPersonResponse> = {},
): ImmichPersonResponse => ({
  external_person_id: "ext-ada",
  name: "Ada Lovelace",
  thumbnail_url:
    "/api/v1/integrations/immich/proxy/people/ext-ada/thumbnail?sig=a",
  is_hidden: false,
  is_favorite: false,
  sync_enabled: false,
  ...over,
});

const peoplePage = (
  people: ImmichPersonResponse[],
  over: Partial<ImmichPeopleListResponse> = {},
): ImmichPeopleListResponse => ({
  people,
  page: 1,
  limit: 100,
  total: people.length,
  has_more: false,
  ...over,
});

const importOk = (
  results: ImmichPeopleImportResponse["results"],
): ImmichPeopleImportResponse => ({ results });

beforeEach(() => {
  vi.clearAllMocks();
  sessionStorage.clear();
  sessionStore.write({ version: 1, accessToken: "a", refreshToken: "r" });
  vi.mocked(api.me).mockResolvedValue(user);
  vi.mocked(api.journals).mockResolvedValue([]);
  vi.mocked(api.people).mockResolvedValue([jane]);
  vi.mocked(api.personGroups).mockResolvedValue([]);
  vi.mocked(api.instanceConfig).mockResolvedValue(configWithImmich);
  vi.mocked(api.integrationStatus).mockResolvedValue(connected);
  vi.mocked(api.immichPeople).mockResolvedValue(peoplePage([immichPerson()]));
  vi.mocked(api.importImmichPeople).mockResolvedValue(
    importOk([
      {
        external_person_id: "ext-ada",
        mode: "create",
        person: { id: "p-new", name: "Ada Lovelace" },
      },
    ]),
  );
});

// base-ui portals (Dialog, Select, Combobox) can leave `pointer-events: none`
// on <body> for a tick after a sibling test unmounts; disable the check so a
// legitimate click is never swallowed by that residue.
const makeUser = () =>
  userEvent.setup({ pointerEventsCheck: PointerEventsCheckLevel.Never });

async function renderPeople() {
  const router = createAppRouter(
    createMemoryHistory({ initialEntries: ["/settings/journaling/people"] }),
  );
  const queryClient = createAppQueryClient();
  queryClient.setDefaultOptions({ queries: { retry: false } });
  render(
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
  await router.load();
  await screen.findByRole("heading", { name: "People" });
  return router;
}

async function openDialog(user: ReturnType<typeof makeUser>) {
  await renderPeople();
  await user.click(
    await screen.findByRole("button", { name: "Import from Immich" }),
  );
  return screen.getByRole("dialog");
}

describe("Library · People · Import from Immich", () => {
  it("hides the action when the instance has no Immich server", async () => {
    vi.mocked(api.instanceConfig).mockResolvedValue(configWithoutImmich);
    await renderPeople();
    await screen.findByText("Jane Doe");
    expect(
      screen.queryByRole("button", { name: "Import from Immich" }),
    ).toBeNull();
    expect(api.integrationStatus).not.toHaveBeenCalled();
  });

  it("hides the action when Immich is configured but not connected", async () => {
    vi.mocked(api.integrationStatus).mockResolvedValue(disconnected);
    await renderPeople();
    await screen.findByText("Jane Doe");
    await waitFor(() => expect(api.integrationStatus).toHaveBeenCalled());
    expect(
      screen.queryByRole("button", { name: "Import from Immich" }),
    ).toBeNull();
  });

  it("lists Immich people and imports a named person as a new create", async () => {
    const user = makeUser();
    const dialog = await openDialog(user);
    expect(await within(dialog).findByText("Ada Lovelace")).toBeTruthy();

    await user.click(
      within(dialog).getByRole("button", { name: "Import 1 person" }),
    );

    await waitFor(() =>
      expect(api.importImmichPeople).toHaveBeenCalledWith({
        people: [
          {
            external_person_id: "ext-ada",
            mode: "create",
            name: "Ada Lovelace",
            sync_enabled: true,
          },
        ],
      }),
    );
    expect(
      await within(dialog).findByText("Created Ada Lovelace"),
    ).toBeTruthy();
  });

  it("uses a bottom sheet on compact viewports", async () => {
    setTestViewportWidth(390);
    const dialog = await openDialog(makeUser());
    expect(dialog.dataset.slot).toBe("drawer-popup");
    expect(await within(dialog).findByText("Ada Lovelace")).toBeTruthy();
  });

  it("keeps browse state when the adaptive primitive swaps", async () => {
    setTestViewportWidth(1440);
    const user = makeUser();
    let dialog = await openDialog(user);
    const search = within(dialog).getByRole("textbox", {
      name: "Search Immich people",
    });
    await user.type(search, "Ada");

    act(() => setTestViewportWidth(390));

    dialog = await screen.findByRole("dialog");
    expect(
      (
        within(dialog).getByRole("textbox", {
          name: "Search Immich people",
        }) as HTMLInputElement
      ).value,
    ).toBe("Ada");
    expect(screen.getAllByRole("dialog")).toHaveLength(1);
  });

  it("passes the trimmed search term to the server after debounce", async () => {
    const user = makeUser();
    const dialog = await openDialog(user);
    await within(dialog).findByText("Ada Lovelace");

    await user.type(
      within(dialog).getByRole("textbox", { name: "Search Immich people" }),
      "  ada  ",
    );

    await waitFor(() =>
      expect(api.immichPeople).toHaveBeenCalledWith(
        expect.objectContaining({ search: "ada" }),
      ),
    );
  });

  it("requires a name before an unnamed face cluster can be imported", async () => {
    vi.mocked(api.immichPeople).mockResolvedValue(
      peoplePage([immichPerson({ external_person_id: "ext-x", name: null })]),
    );
    const user = makeUser();
    const dialog = await openDialog(user);
    await within(dialog).findByText("Unnamed person");

    // Nothing is ready yet — the cluster defaults to Skip.
    expect(
      (
        within(dialog).getByRole("button", {
          name: "Import",
        }) as HTMLButtonElement
      ).disabled,
    ).toBe(true);

    await user.click(
      within(dialog).getByRole("combobox", { name: "Action for this person" }),
    );
    await user.click(await screen.findByRole("option", { name: "Create new" }));

    // Now it is pointed at an action but has no name — import stays blocked.
    expect(within(dialog).getByText("Finish 1 row to import")).toBeTruthy();
    expect(
      (
        within(dialog).getByRole("button", {
          name: "Import",
        }) as HTMLButtonElement
      ).disabled,
    ).toBe(true);

    await user.type(
      within(dialog).getByRole("textbox", { name: "Name this person" }),
      "River",
    );
    await user.click(
      within(dialog).getByRole("button", { name: "Import 1 person" }),
    );

    await waitFor(() =>
      expect(api.importImmichPeople).toHaveBeenCalledWith({
        people: [
          {
            external_person_id: "ext-x",
            mode: "create",
            name: "River",
            sync_enabled: true,
          },
        ],
      }),
    );
  });

  it("links an Immich person to an existing Journiv person", async () => {
    const user = makeUser();
    const dialog = await openDialog(user);
    await within(dialog).findByText("Ada Lovelace");

    await user.click(
      within(dialog).getByRole("combobox", {
        name: "Action for Ada Lovelace",
      }),
    );
    await user.click(
      await screen.findByRole("option", { name: "Link to existing…" }),
    );

    await user.type(
      within(dialog).getByLabelText("Link to Journiv person"),
      "Jane",
    );
    await user.click(await screen.findByRole("option", { name: "Jane Doe" }));

    await user.click(
      within(dialog).getByRole("button", { name: "Import 1 person" }),
    );

    await waitFor(() =>
      expect(api.importImmichPeople).toHaveBeenCalledWith({
        people: [
          {
            external_person_id: "ext-ada",
            mode: "link",
            person_id: "person-jane",
            sync_enabled: true,
          },
        ],
      }),
    );
  });

  it("sends sync_enabled=false when the auto-suggest box is unchecked", async () => {
    const user = makeUser();
    const dialog = await openDialog(user);
    await within(dialog).findByText("Ada Lovelace");

    await user.click(
      within(dialog).getByRole("checkbox", {
        name: /suggest these people/i,
      }),
    );
    await user.click(
      within(dialog).getByRole("button", { name: "Import 1 person" }),
    );

    await waitFor(() =>
      expect(api.importImmichPeople).toHaveBeenCalledWith({
        people: [expect.objectContaining({ sync_enabled: false })],
      }),
    );
  });

  it("reports per-item failures and retries only the failed people", async () => {
    vi.mocked(api.immichPeople).mockResolvedValue(
      peoplePage([
        immichPerson({ external_person_id: "ext-ada", name: "Ada" }),
        immichPerson({ external_person_id: "ext-bob", name: "Bob" }),
      ]),
    );
    vi.mocked(api.importImmichPeople)
      .mockResolvedValueOnce(
        importOk([
          {
            external_person_id: "ext-ada",
            mode: "create",
            person: { id: "p-ada", name: "Ada" },
          },
          {
            external_person_id: "ext-bob",
            mode: "create",
            error: "Immich person is already linked to a Journiv person",
          },
        ]),
      )
      .mockResolvedValueOnce(
        importOk([
          {
            external_person_id: "ext-bob",
            mode: "create",
            person: { id: "p-bob", name: "Bob" },
          },
        ]),
      );

    const user = makeUser();
    const dialog = await openDialog(user);
    await within(dialog).findByText("Ada");
    await user.click(
      within(dialog).getByRole("button", { name: "Import 2 people" }),
    );

    expect(await within(dialog).findByText("Created Ada")).toBeTruthy();
    expect(
      within(dialog).getByText(/Bob: Immich person is already linked/),
    ).toBeTruthy();

    await user.click(
      within(dialog).getByRole("button", { name: "Retry failed" }),
    );

    await waitFor(() =>
      expect(api.importImmichPeople).toHaveBeenLastCalledWith({
        people: [expect.objectContaining({ external_person_id: "ext-bob" })],
      }),
    );
    expect(api.importImmichPeople).toHaveBeenCalledTimes(2);
    expect(await within(dialog).findByText("Created Bob")).toBeTruthy();
  });

  it("shows a reconnect prompt when the people list 400s", async () => {
    vi.mocked(api.immichPeople).mockRejectedValue(
      new ApiError("nope", { status: 400 }),
    );
    const user = makeUser();
    const dialog = await openDialog(user);
    expect(
      await within(dialog).findByText("Immich needs reconnecting"),
    ).toBeTruthy();
  });

  it("does not query Immich people until the dialog is opened", async () => {
    await renderPeople();
    await screen.findByText("Jane Doe");
    await waitFor(() => expect(api.integrationStatus).toHaveBeenCalled());
    expect(api.immichPeople).not.toHaveBeenCalled();
  });
});
