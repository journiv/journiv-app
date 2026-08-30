import { QueryClientProvider } from "@tanstack/react-query";
import { createMemoryHistory, RouterProvider } from "@tanstack/react-router";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { sessionStore } from "../../api/auth/session";
import { api } from "../../api/client/api";
import type {
  ActivityGroupWithActivitiesResponse,
  ActivityResponse,
  UserResponse,
} from "../../api/generated/types.gen";
import { createAppQueryClient } from "../../app/queryClient";
import { createAppRouter } from "../../app/router";

vi.mock("../../api/client/api", () => ({
  api: {
    me: vi.fn(),
    journals: vi.fn(),
    activities: vi.fn(),
    activityGroups: vi.fn(),
    createActivity: vi.fn(),
    updateActivity: vi.fn(),
    deleteActivity: vi.fn(),
    createActivityGroup: vi.fn(),
    updateActivityGroup: vi.fn(),
    deleteActivityGroup: vi.fn(),
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
const run: ActivityResponse = {
  id: "activity-run",
  user_id: user.id,
  name: "Running",
  icon: "footprints",
  color: "#3DBE5D",
  position: 10,
  group_id: "group-wellness",
  created_at: now,
  updated_at: now,
};
const read: ActivityResponse = {
  id: "activity-read",
  user_id: user.id,
  name: "Reading",
  icon: "bookOpen",
  color: "#4F8DF5",
  position: 20,
  group_id: null,
  created_at: now,
  updated_at: now,
};
const wellness: ActivityGroupWithActivitiesResponse = {
  id: "group-wellness",
  user_id: user.id,
  name: "Wellness",
  icon: "heartPulse",
  color_value: 4280391411,
  position: 10,
  activities: [run],
};

beforeEach(() => {
  vi.clearAllMocks();
  sessionStorage.clear();
  sessionStore.write({ version: 1, accessToken: "a", refreshToken: "r" });
  vi.mocked(api.me).mockResolvedValue(user);
  vi.mocked(api.journals).mockResolvedValue([]);
  vi.mocked(api.activities).mockResolvedValue([run, read]);
  vi.mocked(api.activityGroups).mockResolvedValue([wellness]);
  vi.mocked(api.createActivity).mockResolvedValue(run);
  vi.mocked(api.updateActivity).mockResolvedValue(run);
  vi.mocked(api.deleteActivity).mockResolvedValue({ status: "deleted" });
  vi.mocked(api.createActivityGroup).mockResolvedValue(wellness);
  vi.mocked(api.updateActivityGroup).mockResolvedValue(wellness);
  vi.mocked(api.deleteActivityGroup).mockResolvedValue(undefined);
});

async function view(path = "/settings/journaling/activities?q=ignored") {
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
  await screen.findByRole("heading", { name: "Activities" });
  return router;
}

describe("Library · Activities", () => {
  it("opens the real route, marks navigation active, and renders grouped API data", async () => {
    const router = await view();

    expect(router.state.location.pathname).toBe(
      "/settings/journaling/activities",
    );
    expect(
      screen
        .getByRole("link", { name: "Activities" })
        .getAttribute("aria-current"),
    ).toBe("page");
    expect(await screen.findByText("Running")).toBeTruthy();
    expect(screen.getByText("Wellness")).toBeTruthy();
    expect(screen.getByText("Without a group")).toBeTruthy();
    expect(screen.queryByText("Reading")).toBeNull();
  });

  it("opens the ungrouped fallback bucket on demand", async () => {
    await view();
    await userEvent.click(
      screen.getByRole("button", { name: /without a group/i }),
    );
    expect(await screen.findByText("Reading")).toBeTruthy();
  });

  it("keeps the server group count while local search narrows rows", async () => {
    const walk: ActivityResponse = {
      ...run,
      id: "activity-walk",
      name: "Walking",
    };
    vi.mocked(api.activities).mockResolvedValue([run, walk]);
    vi.mocked(api.activityGroups).mockResolvedValue([
      { ...wellness, activities: [run, walk] },
    ]);
    await view();
    await userEvent.type(screen.getByLabelText("Search activities"), "run");

    expect(await screen.findByText("2 activities")).toBeTruthy();
    expect(screen.queryByText("Walking")).toBeNull();
  });

  it("adds an activity to the group selected from its overflow menu", async () => {
    await view();
    await userEvent.click(
      screen.getByRole("button", { name: "Wellness group actions" }),
    );
    await userEvent.click(
      await screen.findByRole("menuitem", { name: "Add activity to group" }),
    );
    const dialog = await screen.findByRole("dialog", { name: "Add activity" });
    expect(
      (within(dialog).getByLabelText("Group") as HTMLSelectElement).value,
    ).toBe(wellness.id);
    await userEvent.type(
      within(dialog).getByLabelText("Activity name"),
      "Stretching",
    );
    await userEvent.click(
      within(dialog).getByRole("button", { name: "Add activity" }),
    );

    await waitFor(() =>
      expect(api.createActivity).toHaveBeenCalledWith({
        name: "Stretching",
        group_id: wellness.id,
        color: null,
        icon: null,
      }),
    );
  });

  it("edits all supported activity fields and can move it out of a group", async () => {
    await view();
    await userEvent.click(
      screen.getByRole("button", { name: "Running actions" }),
    );
    await userEvent.click(
      await screen.findByRole("menuitem", { name: "Edit activity" }),
    );
    const dialog = await screen.findByRole("dialog", { name: "Edit Running" });
    expect(
      (
        within(dialog).getByRole("button", {
          name: "Save",
        }) as HTMLButtonElement
      ).disabled,
    ).toBe(true);
    const name = within(dialog).getByLabelText("Activity name");
    await userEvent.clear(name);
    await userEvent.type(name, "Morning run");
    await userEvent.selectOptions(within(dialog).getByLabelText("Group"), "");
    await userEvent.click(within(dialog).getByLabelText("Blue"));
    await userEvent.click(within(dialog).getByLabelText("Open book"));
    await userEvent.click(within(dialog).getByRole("button", { name: "Save" }));

    await waitFor(() =>
      expect(api.updateActivity).toHaveBeenCalledWith(run.id, {
        name: "Morning run",
        group_id: null,
        color: "#3B82F6",
        icon: "book-open",
      }),
    );
  });

  it("keeps entered values and reports a failed save", async () => {
    vi.mocked(api.createActivity).mockRejectedValueOnce(new Error("network"));
    await view();
    await userEvent.click(screen.getByRole("button", { name: "Add activity" }));
    const dialog = await screen.findByRole("dialog", { name: "Add activity" });
    const input = within(dialog).getByLabelText(
      "Activity name",
    ) as HTMLInputElement;
    await userEvent.type(input, "Swimming");
    await userEvent.click(
      within(dialog).getByRole("button", { name: "Add activity" }),
    );

    expect((await within(dialog).findByRole("alert")).textContent).toContain(
      "could not be saved",
    );
    expect(input.value).toBe("Swimming");
  });

  it("creates an activity group through the reused group manager", async () => {
    await view();
    await userEvent.click(
      screen.getByRole("button", { name: "Manage groups" }),
    );
    let dialog = await screen.findByRole("dialog", { name: "Manage groups" });
    await userEvent.click(
      within(dialog).getByRole("button", { name: "New group" }),
    );
    dialog = await screen.findByRole("dialog", { name: "New group" });
    await userEvent.type(within(dialog).getByLabelText("Group name"), "Work");
    await userEvent.click(within(dialog).getByLabelText("Blue"));
    await userEvent.click(
      within(dialog).getByRole("button", { name: "Create group" }),
    );

    await waitFor(() =>
      expect(api.createActivityGroup).toHaveBeenCalledWith({
        name: "Work",
        color_value: 4282090230,
        icon: null,
        position: 1,
      }),
    );
  });

  it("confirms activity deletion and invalidates the collection", async () => {
    await view();
    await userEvent.click(
      screen.getByRole("button", { name: "Running actions" }),
    );
    await userEvent.click(
      await screen.findByRole("menuitem", { name: "Delete activity…" }),
    );
    const dialog = await screen.findByRole("dialog", {
      name: "Delete Running?",
    });
    await userEvent.click(
      within(dialog).getByRole("button", { name: "Delete activity" }),
    );
    await waitFor(() =>
      expect(api.deleteActivity).toHaveBeenCalledWith(run.id),
    );
    await waitFor(() =>
      expect(vi.mocked(api.activities).mock.calls.length).toBeGreaterThan(1),
    );
  });
});
